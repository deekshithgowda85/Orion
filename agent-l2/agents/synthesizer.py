"""Synthesis agent: assembles the cited FinalReport (large model, max_tokens=8000)."""
import asyncio
import json
import re
from typing import Any

from pydantic import BaseModel, Field

from agents.claims import build_citations
from agents.settings import CONFIDENCE_THRESHOLD, MODEL_LARGE
from agents.state import AgentState
from llm import groq_client
from llm.trace import make_event, now
from models.workflow_models import FinalReport, ReportSection
from prompts.templates import SYNTHESIS_SYSTEM, render

_MARKER = re.compile(r"\[(\d+)\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


class DraftSection(BaseModel):
    """One section as written by the model."""

    heading: str = Field(min_length=2)
    body: str = Field(min_length=10)


class ReportDraft(BaseModel):
    """Arguments of the draft_report tool."""

    executive_summary: str = Field(min_length=20)
    sections: list[DraftSection] = Field(min_length=1, max_length=8)
    risk_flags: list[str] = Field(default_factory=list, max_length=12)


def citation_problems(texts: list[str], n_citations: int) -> list[str]:
    """Return human-readable problems: bad [n] markers and numeric sentences without a citation."""
    problems: list[str] = []
    for text in texts:
        for marker in _MARKER.findall(text):
            if not 1 <= int(marker) <= n_citations:
                problems.append(f"citation [{marker}] does not exist (valid: 1-{n_citations})")
        for sentence in _SENTENCE_SPLIT.split(text):
            if re.search(r"\d", _MARKER.sub("", sentence)) and not _MARKER.search(sentence):
                problems.append(f"numeric sentence without citation: {sentence.strip()[:120]!r}")
    return problems


def _validator(n_citations: int):
    def validate(draft: ReportDraft) -> None:
        texts = [draft.executive_summary, *(s.body for s in draft.sections), *draft.risk_flags]
        problems = citation_problems(texts, n_citations)
        if problems:
            raise ValueError("Citation rules violated:\n- " + "\n- ".join(problems[:8]))
    return validate


def _empty_report(state: AgentState) -> FinalReport:
    """Report used when no verifiable claims exist: honest, uncited, zero confidence."""
    return FinalReport(
        run_id=state["run_id"], ticker=state["ticker"],
        summary=f"No verifiable data could be collected for {state['ticker']}, so no findings are reported.",
        sections=[ReportSection(heading="Data availability",
                                body="The data tools returned no usable evidence for this request.")],
        confidence_score=0.0, conflicts_found=list(state.get("conflict_notes", [])),
        risk_flags=["Report is empty: no verifiable claims were available."],
    )


async def synthesizer_node(state: AgentState) -> AgentState:
    """Write the final report; every numeric statement must carry an inline [n] citation."""
    started = now()
    run_id = state["run_id"]
    events = list(state.get("trace_events", []))
    claims = list(state.get("verified_claims", []))
    news = list(state.get("news_summaries", []))
    citations = state.get("citations") or build_citations(claims, news)

    if not claims and not news:
        report = _empty_report(state)
        events.append(make_event(node="synthesizer", run_id=run_id, started_at=started, detail={"empty_report": True}))
        return {**state, "final_report": report, "trace_events": events}

    number = {c.source_url: c.citation_id for c in citations}
    facts = [{"cite": f"[{number[c.source_url]}]", "status": "VERIFIED" if c.confidence >= CONFIDENCE_THRESHOLD else "UNVERIFIED",
              "metric": c.metric_name, "value": c.value, "unit": c.unit, "period": c.period,
              "confidence": c.confidence, "statement": c.statement, "page_ref": c.page_ref} for c in claims]
    news_facts = [{"sentiment_score": n.sentiment_score,
                   "events": [{"description": e.description, "date": e.date,
                               "cite": f"[{number[e.source_url]}]" if e.source_url in number else None} for e in n.key_events],
                   "entities": [e.name for e in n.entities]} for n in news]
    user = json.dumps({
        "sources": [{"n": c.citation_id, "url": c.source_url, "title": c.title} for c in citations],
        "facts": facts, "news": news_facts, "conflicts": state.get("conflict_notes", []),
        "overall_confidence": state.get("overall_confidence", 0.0),
        "valid_citation_numbers": [int(c.citation_id) for c in citations],
    }, ensure_ascii=False)

    draft = await groq_client.call_structured(
        model=MODEL_LARGE,
        system=render(SYNTHESIS_SYSTEM, ticker=state["ticker"], workflow_type=state["workflow_type"],
                      reviewer_note=state.get("reviewer_note") or "No reviewer note."),
        user=user,
        schema=ReportDraft,
        tool_name="draft_report",
        tool_description="Write the final research report with inline [n] citations.",
        run_id=run_id,
        node="synthesizer",
        events=events,
        max_tokens=8000,
        temperature=0.2,
        validator=_validator(len(citations)),
    )

    low = sum(1 for c in claims if c.confidence < CONFIDENCE_THRESHOLD)
    risk_flags = list(draft.risk_flags)
    if low:
        risk_flags.append(f"{low} claim(s) fell below the {CONFIDENCE_THRESHOLD} confidence threshold and are treated as unverified.")
    report = FinalReport.model_validate({
        "run_id": run_id,
        "ticker": state["ticker"],
        "executive_summary": draft.executive_summary,
        "sections": [ReportSection(heading=s.heading, body=s.body,
                                   citation_ids=sorted(set(_MARKER.findall(s.body)), key=int)).model_dump() for s in draft.sections],
        "citations": [c.model_dump() for c in citations],
        "overall_confidence_score": state.get("overall_confidence", 0.0),
        "conflicts_found": list(state.get("conflict_notes", [])),
        "risk_flags": risk_flags,
        "data_sources": [c.source_url for c in citations],
    })
    events.append(make_event(node="synthesizer", run_id=run_id, started_at=started,
                             detail={"sections": len(report.sections), "citations": len(citations)}))
    return {**state, "final_report": report, "trace_events": events}


if __name__ == "__main__":
    from agents.mock_data import mock_state
    from models.workflow_models import NewsEvent, NewsSummary, VerifiedClaim

    async def _demo() -> None:
        state = mock_state()
        state["verified_claims"] = [
            VerifiedClaim(claim_id="g2-c1", metric_name="revenue", value=11.9, unit="USD billions", period="FY2025",
                          source_type="sec_filing", source_url="https://www.sec.gov/acme-10k", source_title="ACME 10-K FY2025",
                          statement="ACME reported FY2025 revenue of $11.9 billion.", confidence=0.95, page_ref="Page 42"),
            VerifiedClaim(claim_id="g1-c1", metric_name="revenue", value=12500, unit="USD millions", period="FY2025",
                          source_type="financial_api", source_url="https://api.examplefin.test/acme",
                          statement="API reports FY2025 revenue of $12,500 million.", confidence=0.5),
        ]
        state["news_summaries"] = [NewsSummary(goal_id="g3", sentiment_score=0.1, source_urls=["https://news.example.test/acme-inquiry"],
                                               key_events=[NewsEvent(description="Regulator opened an inquiry into pricing practices",
                                                                     date="2026-11-02", source_url="https://news.example.test/acme-inquiry")])]
        state["overall_confidence"] = 0.72
        state["conflict_notes"] = ["revenue FY2025 differs by 5.0% between the API and the 10-K"]
        out = await synthesizer_node(state)
        print(out["final_report"].model_dump_json(indent=2))  # type: ignore[union-attr]

    asyncio.run(_demo())
