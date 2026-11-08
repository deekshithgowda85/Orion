"""Parallel executor node: runs pending sub-goals wave by wave with asyncio.gather."""
import asyncio
from dataclasses import dataclass, field
from typing import Any

from agents import tool_hook
from agents.claims import merge_claims, merge_flags
from agents.executors.filings_executor import extract_filing_claims
from agents.executors.market_data_executor import extract_market_claims
from agents.executors.news_executor import summarise_news
from agents.executors.quant_executor import cross_check_claims
from agents.settings import MAX_CONCURRENCY
from agents.state import AgentState
from llm.groq_client import LLMConfigError
from llm.trace import make_event, now
from models.workflow_models import ConflictFlag, NewsSummary, SubGoal, VerifiedClaim


@dataclass
class _Outcome:
    goal: SubGoal
    claims: list[VerifiedClaim] = field(default_factory=list)
    flags: list[ConflictFlag] = field(default_factory=list)
    news: NewsSummary | None = None
    raw: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    error: BaseException | None = None


async def _run_goal(goal: SubGoal, state: AgentState, claims_snapshot: list[VerifiedClaim],
                    sem: asyncio.Semaphore) -> _Outcome:
    """Run one sub-goal with the executor that matches its agent_type."""
    out = _Outcome(goal)
    ticker, run_id = state["ticker"], state["run_id"]
    async with sem:
        try:
            if goal.agent_type == "quant":
                out.flags = await cross_check_claims(goal, ticker, run_id, claims_snapshot, out.events)
                return out
            out.raw = await tool_hook.get_tool_output(goal, ticker, state["query"], run_id)
            if goal.agent_type == "market_data":
                out.claims = await extract_market_claims(goal, ticker, run_id, out.raw, out.events)
            elif goal.agent_type == "filings":
                out.claims = await extract_filing_claims(goal, ticker, run_id, out.raw, out.events)
            else:
                out.news = await summarise_news(goal, ticker, run_id, out.raw, out.events)
        except LLMConfigError:
            raise
        except Exception as exc:  # one failed goal must not sink the others
            out.error = exc
            out.events.append(make_event(node="parallel_executor", run_id=run_id, started_at=now(), status="failed",
                                         error=f"{type(exc).__name__}: {exc}"[:500], detail={"goal_id": goal.goal_id}))
    return out


async def parallel_executor_node(state: AgentState) -> AgentState:
    """Execute ``pending_goal_ids`` respecting ``depends_on`` (concurrent within each wave)."""
    started = now()
    graph = state["task_graph"]
    assert graph is not None, "planner must run before the executor"
    pending = set(state.get("pending_goal_ids", []))
    completed = set(state.get("completed_goal_ids", []))
    claims = list(state.get("verified_claims", []))
    flags = list(state.get("conflicts", []))
    news = list(state.get("news_summaries", []))
    raw_store = list(state.get("tool_results", []))
    events = list(state.get("trace_events", []))
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    failures: list[str] = []

    for wave in graph.goal_waves(pending, completed):
        outcomes = await asyncio.gather(*(_run_goal(g, state, list(claims), sem) for g in wave))
        for out in outcomes:
            events.extend(out.events)
            claims = merge_claims(claims, out.claims)
            flags = merge_flags(flags, out.flags)
            if out.news:
                news = [n for n in news if n.goal_id != out.goal.goal_id] + [out.news]
            if out.raw:
                raw_store.append({"goal_id": out.goal.goal_id, "agent_type": out.goal.agent_type, "data": out.raw})
            if out.error:
                failures.append(out.goal.goal_id)
            completed.add(out.goal.goal_id)

    if pending and len(failures) == len(pending):
        raise RuntimeError(f"all {len(pending)} sub-goals failed: {failures}")
    events.append(make_event(node="parallel_executor", run_id=state["run_id"], started_at=started,
                             detail={"goals_run": sorted(pending), "failed": failures, "claims_total": len(claims),
                                     "conflicts_total": len(flags)}))
    return {**state, "verified_claims": claims, "conflicts": flags, "news_summaries": news,
            "tool_results": raw_store, "completed_goal_ids": sorted(completed), "trace_events": events}


if __name__ == "__main__":
    from agents.mock_data import mock_get_tool_output, mock_state
    from models.workflow_models import TaskGraph

    async def _demo() -> None:
        tool_hook.get_tool_output = mock_get_tool_output  # type: ignore[assignment]
        state = mock_state()
        state["task_graph"] = TaskGraph(run_id=state["run_id"], goals=[
            SubGoal(goal_id="g1", description="Market metrics", agent_type="market_data"),
            SubGoal(goal_id="g2", description="10-K facts", agent_type="filings"),
            SubGoal(goal_id="g3", description="News", agent_type="news"),
            SubGoal(goal_id="g4", description="Cross-check", agent_type="quant", depends_on=["g1", "g2"]),
        ])
        state["pending_goal_ids"] = ["g1", "g2", "g3", "g4"]
        out = await parallel_executor_node(state)
        print(len(out["verified_claims"]), "claims;", len(out["conflicts"]), "conflicts")
        for flag in out["conflicts"]:
            print(" -", flag.explanation)

    asyncio.run(_demo())
