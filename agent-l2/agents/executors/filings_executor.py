"""Filings executor: parses 10-K / 10-Q / 8-K content and transcripts (fast model)."""
import asyncio
import json
from typing import Any

from agents.executors.common import FilingExtraction, has_data, render_raw, to_claims
from agents.settings import MODEL_FAST
from llm import groq_client
from llm.trace import make_event, now
from models.workflow_models import SubGoal, VerifiedClaim
from prompts.templates import FILINGS_SYSTEM, render


async def extract_filing_claims(
    goal: SubGoal, ticker: str, run_id: str, raw: dict[str, Any], events: list[dict[str, Any]]
) -> list[VerifiedClaim]:
    """Extract claims with page_ref, filing_type and fiscal_period from filing text."""
    started = now()
    if not has_data(raw):
        events.append(make_event(node="filings_executor", run_id=run_id, started_at=started,
                                 detail={"goal_id": goal.goal_id, "skipped": "no tool data"}))
        return []
    text, titles = render_raw(raw)
    result = await groq_client.call_structured(
        model=MODEL_FAST,
        system=render(FILINGS_SYSTEM, ticker=ticker, goal_description=goal.description),
        user=text,
        schema=FilingExtraction,
        tool_name="extract_filing_claims",
        tool_description="Return the claims found in the filing or transcript text.",
        run_id=run_id,
        node="filings_executor",
        events=events,
        max_tokens=3500,
    )
    claims, dropped = to_claims(result.claims, goal_id=goal.goal_id, titles=titles, model=MODEL_FAST)
    events.append(make_event(node="filings_executor", run_id=run_id, started_at=started,
                             detail={"goal_id": goal.goal_id, "claims": len(claims), "dropped_unknown_source": dropped}))
    return claims


if __name__ == "__main__":
    from agents.mock_data import MOCK_RAW, MOCK_REQUEST

    async def _demo() -> None:
        events: list[dict[str, Any]] = []
        goal = SubGoal(goal_id="g2", description="Extract FY2025 revenue, net income and key risks from the 10-K", agent_type="filings")
        claims = await extract_filing_claims(goal, MOCK_REQUEST.ticker, MOCK_REQUEST.run_id, MOCK_RAW["filings"], events)
        print(json.dumps([c.model_dump(mode="json") for c in claims], indent=2))

    asyncio.run(_demo())
