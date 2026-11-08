"""Planner agent (LangGraph node): decomposes the query into a TaskGraph of SubGoals."""
import asyncio
import json
from typing import Any

from pydantic import BaseModel, Field

from agents.settings import MODEL_LARGE
from agents.state import MAX_ITERATIONS, AgentState
from llm import groq_client
from llm.trace import make_event, now
from models.workflow_models import AgentType, SubGoal, TaskGraph
from prompts.templates import PLANNER_SYSTEM, render

WORKFLOW_GUIDANCE = {
    "deep_audit": "Deep audit: 5 to 8 goals covering market_data, filings, news and a quant cross-check.",
    "daily_scan": "Daily scan: 2 to 4 goals, mostly market_data and news; keep it light.",
    "earnings_pulse": "Earnings pulse: 3 to 6 goals focused on the latest earnings filing/transcript, key metrics, news reaction and a quant cross-check.",
}


class SubGoalDraft(BaseModel):
    """LLM-facing sub-goal."""

    goal_id: str = Field(min_length=1, max_length=32)
    description: str = Field(min_length=5)
    agent_type: AgentType
    priority: int = Field(default=3, ge=1, le=5)
    depends_on: list[str] = Field(default_factory=list)


class TaskGraphDraft(BaseModel):
    """Arguments of the create_task_graph tool."""

    goals: list[SubGoalDraft] = Field(min_length=1, max_length=10)


def _make_validator(run_id: str, prior: TaskGraph | None):
    """Return a validator that builds the merged TaskGraph so schema errors feed back to the model."""
    existing = list(prior.goals) if prior else []

    def validate(draft: TaskGraphDraft) -> None:
        clash = {g.goal_id for g in draft.goals} & {g.goal_id for g in existing}
        if clash:
            raise ValueError(f"goal_ids already used: {sorted(clash)}; choose new ids")
        TaskGraph(run_id=run_id, goals=[*existing, *(SubGoal(**g.model_dump()) for g in draft.goals)])

    return validate


async def planner_node(state: AgentState) -> AgentState:
    """Create the initial TaskGraph, or on re-entry turn verifier re-query goals into concrete SubGoals."""
    started = now()
    iteration = state.get("iteration_count", 0) + 1
    events = list(state.get("trace_events", []))
    prior = state.get("task_graph")
    requery = state.get("requery_goals", [])
    run_id = state["run_id"]

    if iteration > 1 and not requery:  # nothing to plan
        events.append(make_event(node="planner", run_id=run_id, started_at=started,
                                 detail={"iteration": iteration, "skipped": "no re-query goals"}))
        return {**state, "iteration_count": iteration, "pending_goal_ids": [], "trace_events": events}

    requery_context = (
        "This is a RE-QUERY pass. Turn each requested re-query goal into a precise sub-goal, keeping its "
        "goal_id and dependencies unless they are invalid. Add no unrelated goals."
        if requery else "This is the initial plan."
    )
    system = render(
        PLANNER_SYSTEM,
        ticker=state["ticker"],
        workflow_type=state["workflow_type"],
        iteration=iteration,
        max_iterations=MAX_ITERATIONS,
        existing_goal_ids=", ".join(g.goal_id for g in prior.goals) if prior else "none",
        workflow_guidance=WORKFLOW_GUIDANCE.get(state["workflow_type"], ""),
        requery_context=requery_context,
    )
    user = json.dumps({
        "query": state["query"],
        "requery_goals": [g.model_dump(mode="json", exclude={"tool_tasks"}) for g in requery],
    }, ensure_ascii=False)

    draft = await groq_client.call_structured(
        model=MODEL_LARGE,
        system=system,
        user=user,
        schema=TaskGraphDraft,
        tool_name="create_task_graph",
        tool_description="Create the research task graph as a list of sub-goals.",
        run_id=run_id,
        node="planner",
        events=events,
        max_tokens=2500,
        temperature=0.2,
        validator=_make_validator(run_id, prior),
    )
    new_goals = [SubGoal(**g.model_dump()) for g in draft.goals]
    graph = TaskGraph(run_id=run_id, goals=[*(prior.goals if prior else []), *new_goals])
    events.append(make_event(node="planner", run_id=run_id, started_at=started,
                             detail={"iteration": iteration, "new_goals": [g.goal_id for g in new_goals]}))
    return {**state, "task_graph": graph, "pending_goal_ids": [g.goal_id for g in new_goals],
            "iteration_count": iteration, "requery_goals": [], "trace_events": events}


if __name__ == "__main__":
    from agents.mock_data import mock_state

    async def _demo() -> None:
        out = await planner_node(mock_state())
        print(out["task_graph"].model_dump_json(indent=2, exclude={"goals": {"__all__": {"tool_tasks"}}}))  # type: ignore[union-attr]

    asyncio.run(_demo())
