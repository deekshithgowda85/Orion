"""Verifier node: reviews claims and conflicts, enforces source authority, decides on re-query."""
import asyncio
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from agents.claims import build_citations
from agents.settings import CONFIDENCE_THRESHOLD, MODEL_LARGE
from agents.state import MAX_ITERATIONS, AgentState
from llm import groq_client
from llm.trace import make_event, now
from models.workflow_models import SubGoal, VerificationResult, VerifiedClaim
from prompts.templates import VERIFIER_SYSTEM, render

#: Highest to lowest authority: SEC filings > transcripts > financial APIs > news > other.
AUTHORITY_ORDER = ["sec_filing", "transcript", "financial_api", "news", "other"]
#: A claim can never be more confident than its source type allows.
AUTHORITY_CEILING = {"sec_filing": 1.0, "transcript": 0.9, "financial_api": 0.85, "news": 0.7, "other": 0.5}
MAX_REQUERY_GOALS = 4


class ClaimAssessment(BaseModel):
    """LLM verdict for one claim."""

    claim_id: str
    adjusted_confidence: float = Field(ge=0.0, le=1.0)
    verdict: Literal["accepted", "downgraded", "rejected"]
    reason: str
    requery_hint: str | None = None


class VerifierAssessment(BaseModel):
    """Arguments of the assess_claims tool."""

    assessments: list[ClaimAssessment] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)


def _rank(claim: VerifiedClaim) -> int:
    """Lower number = higher authority."""
    return AUTHORITY_ORDER.index(claim.source_type)


def _requery_goals(low: list[VerifiedClaim], hints: dict[str, str], graph_descriptions: str,
                   iteration: int, has_conflicts: bool, conflict_ids: set[str]) -> list[SubGoal]:
    """Build re-query SubGoals for low-confidence claims (one per metric/period, never repeated)."""
    goals: list[SubGoal] = []
    seen: set[str] = set()
    for claim in low:
        key = f"{claim.metric_name}|{claim.period or 'n/a'}".lower()
        marker = f"[requery-key:{key}]"
        if key in seen or marker in graph_descriptions:
            continue  # already re-queried in an earlier pass: do not loop on the same gap
        seen.add(key)
        hint = hints.get(claim.claim_id) or "Find primary-source evidence for this figure."
        goals.append(SubGoal(
            goal_id=f"rq{iteration}-{len(goals) + 1}",
            description=f"Re-verify {claim.metric_name} for {claim.period or 'the stated period'}. {hint} {marker}",
            agent_type="market_data" if claim.source_type in {"sec_filing", "transcript"} else "filings",
            priority=1 if claim.claim_id in conflict_ids else 2,
        ))
        if len(goals) >= MAX_REQUERY_GOALS - 1:
            break
    if goals and has_conflicts:
        goals.append(SubGoal(goal_id=f"rq{iteration}-q", description="Re-run the numeric cross-check on the new evidence.",
                             agent_type="quant", priority=1, depends_on=[g.goal_id for g in goals]))
    return goals


async def verifier_node(state: AgentState) -> AgentState:
    """Verify claims, apply source authority, and set ``needs_requery`` / ``requery_goals``."""
    started = now()
    run_id = state["run_id"]
    iteration = state.get("iteration_count", 1)
    events = list(state.get("trace_events", []))
    claims = list(state.get("verified_claims", []))
    flags = list(state.get("conflicts", []))
    news = list(state.get("news_summaries", []))
    graph = state.get("task_graph")

    if not claims:  # nothing to verify (for example Layer 3 tools returned no data): re-querying cannot help
        events.append(make_event(node="verifier", run_id=run_id, started_at=started,
                                 detail={"iteration": iteration, "skipped": "no claims"}))
        return {**state, "verified_claims": [], "verifications": [], "overall_confidence": 0.0,
                "needs_requery": False, "requery_goals": [], "citations": build_citations([], news),
                "conflict_notes": ["No verifiable claims were returned by the data tools; confidence is zero."],
                "trace_events": events}

    payload = {
        "claims": [{"claim_id": c.claim_id, "metric_name": c.metric_name, "value": c.value, "unit": c.unit,
                    "period": c.period, "source_type": c.source_type, "source_url": c.source_url,
                    "extractor_confidence": c.confidence, "page_ref": c.page_ref} for c in claims],
        "conflicts": [f.explanation for f in flags],
        "news": [{"sentiment_score": n.sentiment_score, "key_events": [e.description for e in n.key_events]} for n in news],
    }
    verdicts = await groq_client.call_structured(
        model=MODEL_LARGE,
        system=render(VERIFIER_SYSTEM, ticker=state["ticker"], iteration=iteration, max_iterations=MAX_ITERATIONS,
                      confidence_threshold=CONFIDENCE_THRESHOLD, authority_order=" > ".join(AUTHORITY_ORDER)),
        user=json.dumps(payload, ensure_ascii=False),
        schema=VerifierAssessment,
        tool_name="assess_claims",
        tool_description="Assess every claim: adjusted confidence, verdict and reason.",
        run_id=run_id,
        node="verifier",
        events=events,
        max_tokens=4000,
    )
    by_id = {a.claim_id: a for a in verdicts.assessments}

    # 1) LLM verdict (downgrade only) capped by source authority
    kept: list[VerifiedClaim] = []
    notes: dict[str, str] = {}
    hints: dict[str, str] = {}
    for claim in claims:
        a = by_id.get(claim.claim_id)
        if a and a.verdict == "rejected":
            continue
        confidence = min(claim.confidence, a.adjusted_confidence if a else claim.confidence,
                         AUTHORITY_CEILING[claim.source_type])
        notes[claim.claim_id] = a.reason if a else "not individually assessed"
        if a and a.requery_hint:
            hints[claim.claim_id] = a.requery_hint
        kept.append(claim.model_copy(update={"confidence": round(confidence, 3)}))

    # 2) Conflict resolution by authority: only the top-authority source keeps its confidence
    conflict_ids: set[str] = set()
    conflict_notes: list[str] = []
    for flag in flags:
        members = [c for c in kept if c.claim_id in flag.claim_ids]
        if len(members) < 2:
            continue
        top = min(_rank(c) for c in members)
        winners = [c for c in members if _rank(c) == top]
        tie = len({c.numeric_value() for c in winners}) > 1
        cap = 0.55 if tie else 0.5
        for c in members:
            if _rank(c) != top or tie:
                conflict_ids.add(c.claim_id)
                kept = [k.model_copy(update={"confidence": min(k.confidence, cap)}) if k.claim_id == c.claim_id else k for k in kept]
        outcome = ("unresolved: same-authority sources disagree" if tie
                   else f"higher-authority source ({winners[0].source_type}) preferred")
        conflict_notes.append(f"{flag.explanation} -> {outcome}")
    conflict_notes.extend(verdicts.contradictions)

    # 3) Scores, re-query decision
    overall = round(sum(c.confidence for c in kept) / len(kept), 3) if kept else 0.0
    low = [c for c in kept if c.confidence < CONFIDENCE_THRESHOLD]
    descriptions = " ".join(g.description for g in graph.goals) if graph else ""
    goals = _requery_goals(low, hints, descriptions, iteration, bool(flags), conflict_ids) if iteration < MAX_ITERATIONS else []
    verifications = [VerificationResult(
        claim_id=c.claim_id, claim_text=c.statement or f"{c.metric_name} {c.value} {c.unit or ''} ({c.period or 'n/a'})".strip(),
        confidence=c.confidence, is_conflicted=c.claim_id in conflict_ids,
        notes=f"{notes.get(c.claim_id, '')} | source: {c.source_url}".strip(" |")) for c in kept]

    events.append(make_event(node="verifier", run_id=run_id, started_at=started, detail={
        "iteration": iteration, "claims_in": len(claims), "claims_kept": len(kept), "low_confidence": len(low),
        "overall_confidence": overall, "requery_goals": [g.goal_id for g in goals]}))
    return {**state, "verified_claims": kept, "verifications": verifications, "overall_confidence": overall,
            "needs_requery": bool(goals), "requery_goals": goals, "citations": build_citations(kept, news),
            "conflict_notes": conflict_notes, "trace_events": events}


if __name__ == "__main__":
    from agents.mock_data import mock_state
    from models.workflow_models import ConflictFlag, TaskGraph

    async def _demo() -> None:
        state = mock_state()
        state["iteration_count"] = 1
        state["task_graph"] = TaskGraph(run_id=state["run_id"], goals=[
            SubGoal(goal_id="g1", description="Market metrics", agent_type="market_data")])
        mk = lambda cid, url, st, val, unit: VerifiedClaim(  # noqa: E731
            claim_id=cid, metric_name="revenue", value=val, unit=unit, period="FY2025",
            source_type=st, source_url=url, confidence=0.9)
        state["verified_claims"] = [mk("g1-c1", "https://api.examplefin.test/acme", "financial_api", 12500, "USD millions"),
                                    mk("g2-c1", "https://www.sec.gov/acme-10k", "sec_filing", 11.9, "USD billions")]
        state["conflicts"] = [ConflictFlag(metric_name="revenue", period="FY2025", unit="usd", claim_ids=["g1-c1", "g2-c1"],
                                           values={"g1-c1": 12.5e9, "g2-c1": 11.9e9}, pct_difference=5.04,
                                           severity="low", explanation="revenue FY2025 differs by 5.0% across sources")]
        out = await verifier_node(state)
        print("overall:", out["overall_confidence"], "| needs_requery:", out["needs_requery"])
        for goal in out["requery_goals"]:
            print(" requery:", goal.goal_id, goal.agent_type, goal.description)

    asyncio.run(_demo())
