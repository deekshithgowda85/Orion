"""LangGraph state shared by all agent nodes (kept free of heavy imports)."""
from typing import Any, TypedDict

from models.workflow_models import (
    CitationRef,
    ConflictFlag,
    FinalReport,
    NewsSummary,
    ResearchRequest,
    SubGoal,
    TaskGraph,
    VerificationResult,
    VerifiedClaim,
)

MAX_ITERATIONS: int = 5


class AgentState(TypedDict, total=False):
    """Explicit graph state. Nodes read what they need and return the updated state."""

    # --- required by the spec ---
    run_id: str
    tenant_id: str
    query: str
    task_graph: TaskGraph | None
    tool_results: list[dict[str, Any]]  # raw tool payloads per goal (Layer 3)
    verified_claims: list[VerifiedClaim]
    conflicts: list[ConflictFlag]
    final_report: FinalReport | None
    trace_events: list[dict[str, Any]]
    iteration_count: int
    # --- additional working fields ---
    ticker: str
    workflow_type: str
    news_summaries: list[NewsSummary]
    completed_goal_ids: list[str]
    pending_goal_ids: list[str]
    requery_goals: list[SubGoal]
    verifications: list[VerificationResult]
    citations: list[CitationRef]
    conflict_notes: list[str]
    overall_confidence: float
    needs_requery: bool
    reviewer_note: str


def initial_state(request: ResearchRequest, iteration: int = 0) -> AgentState:
    """Build a fresh :class:`AgentState` for a research request."""
    return AgentState(
        run_id=request.run_id,
        tenant_id=request.tenant_id,
        query=request.query,
        ticker=request.ticker,
        workflow_type=request.workflow_type,
        task_graph=None,
        tool_results=[],
        verified_claims=[],
        conflicts=[],
        final_report=None,
        trace_events=[],
        iteration_count=iteration,
        news_summaries=[],
        completed_goal_ids=[],
        pending_goal_ids=[],
        requery_goals=[],
        verifications=[],
        citations=[],
        conflict_notes=[],
        overall_confidence=0.0,
        needs_requery=False,
        reviewer_note="",
    )
