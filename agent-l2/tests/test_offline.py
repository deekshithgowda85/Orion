"""Offline tests: no Groq key, Temporal server or database required.

Run:  python -m tests.test_offline      (or: pytest -q)

The Groq call layer is replaced by a deterministic fake that returns schema-valid
objects, so these tests exercise the real planner/executor/verifier/synthesizer
logic, the LangGraph wiring (including the self-correction loop) and the
Temporal activity glue.
"""
import asyncio
import json
import os
import tempfile
from typing import Any

from temporalio.testing import ActivityEnvironment

from agents import tool_hook
from agents.executors.common import ClaimDraft, ClaimExtraction, FilingClaimDraft, FilingExtraction
from agents.executors.news_executor import NewsDraft
from agents.executors.quant_executor import ClaimGroup, ClaimGrouping, compare_group, normalise
from agents.graph import route_after_verifier, run_research_graph_state
from agents.mock_data import MOCK_REQUEST, mock_get_tool_output
from agents.planner import SubGoalDraft, TaskGraphDraft
from agents.synthesizer import DraftSection, ReportDraft, citation_problems
from agents.verifier import ClaimAssessment, VerifierAssessment
from llm import groq_client
from llm.trace import make_event, now
from models.workflow_models import (
    ApprovalDecision, AgentProgress, AuditLogInput, ExecutorInput, NamedEntity, NewsEvent, PlannerInput,
    SubGoal, SynthesisInput, TaskGraph, VerifiedClaim, VerifierInput,
)

API_URL = "https://api.examplefin.test/v1/acme/financials"
SEC_URL = "https://www.sec.gov/Archives/edgar/data/0000000/acme-10k-fy2025.htm"
NEWS_URL = "https://news.example.test/acme-inquiry"
CALLS: list[str] = []


def _fake_graph(data: dict, system: str) -> TaskGraphDraft:
    if data["requery_goals"]:
        keys = ("goal_id", "description", "agent_type", "priority", "depends_on")
        return TaskGraphDraft(goals=[SubGoalDraft(**{k: g[k] for k in keys}) for g in data["requery_goals"]])
    return TaskGraphDraft(goals=[
        SubGoalDraft(goal_id="g1", description="Collect FY2025 financial metrics", agent_type="market_data", priority=1),
        SubGoalDraft(goal_id="g2", description="Extract FY2025 facts from the 10-K", agent_type="filings", priority=1),
        SubGoalDraft(goal_id="g3", description="Summarise recent news", agent_type="news", priority=2),
        SubGoalDraft(goal_id="g4", description="Cross-check revenue across sources", agent_type="quant", depends_on=["g1", "g2"]),
    ])


def _fake_assess(data: dict, system: str) -> VerifierAssessment:
    return VerifierAssessment(assessments=[
        ClaimAssessment(claim_id=c["claim_id"], adjusted_confidence=c["extractor_confidence"], verdict="accepted",
                        reason="consistent with source", requery_hint="Check the 10-K" if c["source_type"] == "financial_api" else None)
        for c in data["claims"]])


def _fake_group(data: dict, system: str) -> ClaimGrouping:
    ids = [c["claim_id"] for c in data["claims"] if c["metric_name"] == "revenue"]
    return ClaimGrouping(groups=[ClaimGroup(metric_name="revenue", period="FY2025", claim_ids=ids)] if len(ids) > 1 else [])


def _fake_report(data: dict, system: str) -> ReportDraft:
    assert len(data["valid_citation_numbers"]) >= 3
    return ReportDraft(
        executive_summary="ACME reported FY2025 revenue of $11.9 billion in its 10-K [2]. Sources disagree on revenue by about 5% [1][2].",
        sections=[DraftSection(heading="Financial Performance",
                               body="The financial API and the 10-K disagree on FY2025 revenue [1][2]. The higher-authority filing is preferred [2]."),
                  DraftSection(heading="Risks", body="A regulator opened an inquiry into pricing practices [3].")],
        risk_flags=["Regulatory inquiry may lead to fines or product changes [3]."])


FAKES = {
    "create_task_graph": _fake_graph,
    "extract_market_claims": lambda d, s: ClaimExtraction(claims=[ClaimDraft(
        metric_name="revenue", value=12500, unit="USD millions", period="FY2025", source_url=API_URL,
        confidence=0.9, statement="API reports FY2025 revenue of $12,500 million.")]),
    "extract_filing_claims": lambda d, s: FilingExtraction(claims=[FilingClaimDraft(
        metric_name="revenue", value=11.9, unit="USD billions", period="FY2025", source_url=SEC_URL, confidence=0.95,
        statement="ACME reported FY2025 revenue of $11.9 billion.", page_ref="Page 42", filing_type="10-K", fiscal_period="FY2025")]),
    "summarize_news": lambda d, s: NewsDraft(sentiment_score=0.1, key_events=[NewsEvent(
        description="Regulator opened an inquiry into pricing", date="2026-11-02", source_url=NEWS_URL)],
        entities=[NamedEntity(name="ACME", entity_type="company")]),
    "group_numeric_claims": _fake_group,
    "assess_claims": _fake_assess,
    "draft_report": _fake_report,
}


async def fake_call_structured(*, model, system, user, schema, tool_name, tool_description, run_id, node, events,
                               max_tokens=2048, temperature=0.1, max_attempts=3, validator=None):
    """Deterministic stand-in for llm.groq_client.call_structured."""
    CALLS.append(tool_name)
    data = json.loads(user) if user.lstrip().startswith("{") else user
    result = FAKES[tool_name](data, system)
    assert isinstance(result, schema)
    if validator:
        validator(result)
    events.append(make_event(node=node, run_id=run_id, started_at=now(), event_type="llm_call", model=model,
                             prompt_tokens=10, completion_tokens=5))
    return result


def _patch() -> None:
    groq_client.call_structured = fake_call_structured  # type: ignore[assignment]
    tool_hook.get_tool_output = mock_get_tool_output  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
def test_task_graph_waves_and_validation() -> None:
    graph = TaskGraph(run_id="r", goals=[
        SubGoal(goal_id="a", description="x", agent_type="market_data"),
        SubGoal(goal_id="b", description="x", agent_type="filings"),
        SubGoal(goal_id="c", description="x", agent_type="quant", depends_on=["a", "b"])])
    assert [[g.goal_id for g in w] for w in graph.goal_waves()] == [["a", "b"], ["c"]]
    assert [[g.goal_id for g in w] for w in graph.goal_waves({"c"}, {"a", "b"})] == [["c"]]
    for bad in ([SubGoal(goal_id="a", description="x", agent_type="news", depends_on=["a"])],
                [SubGoal(goal_id="a", description="x", agent_type="news", depends_on=["zzz"])]):
        try:
            TaskGraph(run_id="r", goals=bad)
        except ValueError:
            continue
        raise AssertionError("invalid graph accepted")


def test_conflict_math() -> None:
    assert normalise(12500, "USD millions") == (12.5e9, "usd")
    assert normalise(11.9, "$B") == (11.9e9, "usd")

    def claim(cid: str, value: float, unit: str) -> VerifiedClaim:
        return VerifiedClaim(claim_id=cid, metric_name="revenue", value=value, unit=unit, period="FY2025",
                             source_url=f"https://x.test/{cid}", confidence=0.9)

    group = ClaimGroup(metric_name="revenue", period="FY2025", claim_ids=["a", "b"])
    flag = compare_group(group, {"a": claim("a", 12500, "USD millions"), "b": claim("b", 11.9, "USD billions")})
    assert flag is not None and 5.0 < flag.pct_difference < 5.1
    assert compare_group(group, {"a": claim("a", 12500, "USD millions"), "b": claim("b", 12.4, "USD billions")}) is None
    assert compare_group(group, {"a": claim("a", 12500, "USD millions"), "b": claim("b", 12, "percent")}) is None


def test_citation_rules() -> None:
    assert citation_problems(["Revenue was $11.9 billion [1]. Outlook is stable."], 2) == []
    assert citation_problems(["Revenue was $11.9 billion."], 2)
    assert citation_problems(["Revenue was $11.9 billion [5]."], 2)


def test_graph_end_to_end_with_self_correction() -> None:
    _patch()
    CALLS.clear()
    state = asyncio.run(run_research_graph_state(MOCK_REQUEST))
    report = state["final_report"]
    assert report is not None
    assert state["iteration_count"] == 2, "verifier should route back to the planner exactly once"
    assert CALLS.count("create_task_graph") == 2 and CALLS.count("draft_report") == 1
    assert {g.goal_id for g in state["task_graph"].goals} >= {"g1", "g2", "g3", "g4", "rq1-1", "rq1-q"}
    assert report.conflicts_found and any("higher-authority" in c for c in report.conflicts_found)
    assert 0 < report.confidence_score < 1
    assert [c.citation_id for c in report.citations] == ["1", "2", "3", "4"]
    assert "[2]" in report.summary and report.data_sources[0] == API_URL
    assert any(s.citation_ids for s in report.sections)
    assert any(e["node"] == "verifier" for e in state["trace_events"])
    assert route_after_verifier({"needs_requery": True, "iteration_count": 5}) == "synthesizer"
    assert route_after_verifier({"needs_requery": True, "iteration_count": 2}) == "planner"


def test_no_tool_data_yields_honest_empty_report() -> None:
    _patch()

    async def no_data(goal, ticker, query, run_id):  # Layer 3 not wired yet
        return {}

    tool_hook.get_tool_output = no_data  # type: ignore[assignment]
    CALLS.clear()
    state = asyncio.run(run_research_graph_state(MOCK_REQUEST))
    assert state["iteration_count"] == 1 and "draft_report" not in CALLS
    assert state["final_report"].confidence_score == 0.0
    assert not state["final_report"].citations


def test_temporal_activities_via_activity_environment() -> None:
    _patch()

    async def scenario() -> None:
        env = ActivityEnvironment()
        from activities.implementations import (audit_log_activity, parallel_executor_activity, planner_activity,
                                                synthesis_activity, verifier_activity)
        plan = await env.run(planner_activity, PlannerInput(request=MOCK_REQUEST))
        assert plan.pending_goal_ids == ["g1", "g2", "g3", "g4"] and plan.trace.token_count == 15
        ex = await env.run(parallel_executor_activity, ExecutorInput(
            request=MOCK_REQUEST, task_graph=plan.task_graph, goal_ids=plan.pending_goal_ids, progress=AgentProgress()))
        assert len(ex.progress.claims) == 2 and len(ex.progress.conflict_flags) == 1
        ver = await env.run(verifier_activity, VerifierInput(
            request=MOCK_REQUEST, task_graph=plan.task_graph, progress=ex.progress, iteration=1))
        assert ver.needs_requery and ver.requery_goals and ver.citations
        ver_final = ver.model_copy(update={"needs_requery": False})
        syn = await env.run(synthesis_activity, SynthesisInput(
            request=MOCK_REQUEST, task_graph=plan.task_graph, verification=ver_final,
            approval=ApprovalDecision(approved=True, reviewer="tester", comment="Looks fine")))
        report = syn.report.model_copy(update={"trace_log": [plan.trace, ex.trace, ver.trace, syn.trace]})
        with tempfile.TemporaryDirectory() as tmp:
            os.environ.pop("NEON_DATABASE_URL", None)
            os.environ["AUDIT_LOCAL_DIR"] = tmp
            audit = await env.run(audit_log_activity, AuditLogInput(
                request=MOCK_REQUEST, report=report, approval=ApprovalDecision(), agent_events=plan.agent_events + ex.agent_events))
            assert audit.stored_in == "local_file" and audit.records_written >= 6
            lines = open(os.path.join(tmp, "demo-tenant", "mock-run-1.jsonl"), encoding="utf-8").read().splitlines()
            assert len(lines) == audit.records_written and all(json.loads(line) for line in lines)

    asyncio.run(scenario())


def test_neon_dsn_cleaning() -> None:
    from activities.audit_store import clean_dsn
    cleaned = clean_dsn("postgresql://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require")
    assert "channel_binding" not in cleaned and "sslmode=require" in cleaned


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
