"""Market-data executor: extracts structured financial metrics (fast model)."""
import asyncio
import json
from typing import Any

from agents.executors.common import ClaimExtraction, has_data, render_raw, to_claims
from agents.settings import MODEL_FAST
from llm import groq_client
from llm.trace import make_event, now
from models.workflow_models import SubGoal, VerifiedClaim
from prompts.templates import MARKET_DATA_SYSTEM, render


async def extract_market_claims(
    goal: SubGoal, ticker: str, run_id: str, raw: dict[str, Any], events: list[dict[str, Any]]
) -> list[VerifiedClaim]:
    """Extract metric claims (value, unit, period, source_url, confidence) from raw market data."""
    started = now()
    if not has_data(raw):
        events.append(make_event(node="market_data_executor", run_id=run_id, started_at=started,
                                 detail={"goal_id": goal.goal_id, "skipped": "no tool data"}))
        return []
    text, titles = render_raw(raw)
    result = await groq_client.call_structured(
        model=MODEL_FAST,
        system=render(MARKET_DATA_SYSTEM, ticker=ticker, goal_description=goal.description),
        user=text,
        schema=ClaimExtraction,
        tool_name="extract_market_claims",
        tool_description="Return the financial metrics found in the source data.",
        run_id=run_id,
        node="market_data_executor",
        events=events,
        max_tokens=3000,
    )
    claims, dropped = to_claims(result.claims, goal_id=goal.goal_id, titles=titles,
                                model=MODEL_FAST, source_type="financial_api")
    events.append(make_event(node="market_data_executor", run_id=run_id, started_at=started,
                             detail={"goal_id": goal.goal_id, "claims": len(claims), "dropped_unknown_source": dropped}))
    return claims


if __name__ == "__main__":
    from agents.mock_data import MOCK_RAW, MOCK_REQUEST

    async def _demo() -> None:
        events: list[dict[str, Any]] = []
        goal = SubGoal(goal_id="g1", description="Get FY2025 revenue, net income and EPS", agent_type="market_data")
        claims = await extract_market_claims(goal, MOCK_REQUEST.ticker, MOCK_REQUEST.run_id, MOCK_RAW["market_data"], events)
        print(json.dumps([c.model_dump(mode="json") for c in claims], indent=2))

    asyncio.run(_demo())
