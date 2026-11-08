"""News executor: sentiment, key events and named entities (fast model)."""
import asyncio
from typing import Any

from pydantic import BaseModel, Field

from agents.executors.common import has_data, render_raw
from agents.settings import MODEL_FAST
from llm import groq_client
from llm.trace import make_event, now
from models.workflow_models import NamedEntity, NewsEvent, NewsSummary, SubGoal
from prompts.templates import NEWS_SYSTEM, render


class NewsDraft(BaseModel):
    """Tool schema for summarize_news."""

    sentiment_score: float = Field(ge=-1.0, le=1.0)
    key_events: list[NewsEvent] = Field(default_factory=list, max_length=8)
    entities: list[NamedEntity] = Field(default_factory=list, max_length=30)


async def summarise_news(
    goal: SubGoal, ticker: str, run_id: str, raw: dict[str, Any], events: list[dict[str, Any]]
) -> NewsSummary | None:
    """Return a :class:`NewsSummary`, or None when no news data was supplied."""
    started = now()
    if not has_data(raw):
        events.append(make_event(node="news_executor", run_id=run_id, started_at=started,
                                 detail={"goal_id": goal.goal_id, "skipped": "no tool data"}))
        return None
    text, titles = render_raw(raw)
    draft = await groq_client.call_structured(
        model=MODEL_FAST,
        system=render(NEWS_SYSTEM, ticker=ticker, goal_description=goal.description),
        user=text,
        schema=NewsDraft,
        tool_name="summarize_news",
        tool_description="Return sentiment, key events and named entities from the news.",
        run_id=run_id,
        node="news_executor",
        events=events,
        max_tokens=2500,
    )
    key_events = [e.model_copy(update={"source_url": e.source_url if e.source_url in titles else None})
                  for e in draft.key_events]
    summary = NewsSummary(goal_id=goal.goal_id, sentiment_score=draft.sentiment_score, key_events=key_events,
                          entities=draft.entities, source_urls=list(titles))
    events.append(make_event(node="news_executor", run_id=run_id, started_at=started,
                             detail={"goal_id": goal.goal_id, "events": len(key_events), "sentiment": draft.sentiment_score}))
    return summary


if __name__ == "__main__":
    from agents.mock_data import MOCK_RAW, MOCK_REQUEST

    async def _demo() -> None:
        goal = SubGoal(goal_id="g3", description="Summarise recent news sentiment and key events", agent_type="news")
        summary = await summarise_news(goal, MOCK_REQUEST.ticker, MOCK_REQUEST.run_id, MOCK_RAW["news"], [])
        print(summary.model_dump_json(indent=2) if summary else "no data")

    asyncio.run(_demo())
