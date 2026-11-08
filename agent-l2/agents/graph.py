"""LangGraph assembly.

START -> planner -> parallel_executor -> verifier --(needs_requery?)--> planner (loop)
                                                   \\--(otherwise)----> synthesizer -> END
"""
import asyncio
from typing import Literal

from langgraph.graph import END, START, StateGraph

from agents.parallel_executor import parallel_executor_node
from agents.planner import planner_node
from agents.state import MAX_ITERATIONS, AgentState, initial_state
from agents.synthesizer import synthesizer_node
from agents.verifier import verifier_node
from models.workflow_models import FinalReport, ResearchRequest


def route_after_verifier(state: AgentState) -> Literal["planner", "synthesizer"]:
    """Self-correction edge: loop back to the planner until confident or MAX_ITERATIONS is reached."""
    if state.get("needs_requery") and state.get("iteration_count", 0) < MAX_ITERATIONS:
        return "planner"
    return "synthesizer"


def build_graph():
    """Compile the research StateGraph."""
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner_node)
    builder.add_node("parallel_executor", parallel_executor_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("synthesizer", synthesizer_node)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "parallel_executor")
    builder.add_edge("parallel_executor", "verifier")
    builder.add_conditional_edges("verifier", route_after_verifier,
                                  {"planner": "planner", "synthesizer": "synthesizer"})
    builder.add_edge("synthesizer", END)
    return builder.compile()


async def run_research_graph_state(request: ResearchRequest) -> AgentState:
    """Run the whole graph and return the final state (useful for debugging/tests)."""
    graph = build_graph()
    return await graph.ainvoke(initial_state(request), config={"recursion_limit": 60})


async def run_research_graph(request: ResearchRequest) -> FinalReport:
    """Run the full research graph for ``request`` and return the validated FinalReport."""
    state = await run_research_graph_state(request)
    report = state["final_report"]
    assert report is not None
    return report


if __name__ == "__main__":
    from agents import tool_hook
    from agents.mock_data import MOCK_REQUEST, mock_get_tool_output

    async def _demo() -> None:
        tool_hook.get_tool_output = mock_get_tool_output  # type: ignore[assignment]  # fixtures instead of Layer 3
        report = await run_research_graph(MOCK_REQUEST)
        print(report.model_dump_json(indent=2))

    asyncio.run(_demo())
