"""Quant executor: cross-checks numeric claims across sources (large model).

The LLM only *groups* claims that describe the same metric and period; the
unit normalisation and the percentage arithmetic are done in code so the
>5% rule is exact and auditable.
"""
import asyncio
import json
import re
from typing import Any

from pydantic import BaseModel, Field

from agents.settings import CONFLICT_THRESHOLD_PCT, MODEL_LARGE
from llm import groq_client
from llm.trace import make_event, now
from models.workflow_models import ConflictFlag, SubGoal, VerifiedClaim
from prompts.templates import QUANT_SYSTEM, render

_SCALES = {"k": 1e3, "thousand": 1e3, "thousands": 1e3, "m": 1e6, "mm": 1e6, "mn": 1e6, "million": 1e6,
           "millions": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "billions": 1e9, "t": 1e12, "tn": 1e12,
           "trillion": 1e12}
_CURRENCY = {"$": "usd", "usd": "usd", "us": "usd", "dollar": "usd", "dollars": "usd"}


class ClaimGroup(BaseModel):
    """Claims describing the same metric and period."""

    metric_name: str
    period: str | None = None
    claim_ids: list[str] = Field(min_length=2)


class ClaimGrouping(BaseModel):
    """Tool schema for group_numeric_claims."""

    groups: list[ClaimGroup] = Field(default_factory=list)


def normalise(value: float, unit: str | None) -> tuple[float, str]:
    """Scale ``value`` to base units and return (scaled value, canonical base unit)."""
    scale, base = 1.0, []
    for token in re.findall(r"[a-z]+|[%$]", (unit or "").lower()):
        if token in _SCALES:
            scale *= _SCALES[token]
        else:
            base.append(_CURRENCY.get(token, token))
    return value * scale, " ".join(dict.fromkeys(base)) or "unitless"


def compare_group(group: ClaimGroup, by_id: dict[str, VerifiedClaim]) -> ConflictFlag | None:
    """Return a :class:`ConflictFlag` when a group's values differ by more than the threshold."""
    members = [by_id[i] for i in dict.fromkeys(group.claim_ids) if i in by_id and by_id[i].numeric_value() is not None]
    if len(members) < 2:
        return None
    normed = {m.claim_id: normalise(m.numeric_value(), m.unit) for m in members}  # type: ignore[arg-type]
    if len({unit for _, unit in normed.values()}) != 1:
        return None  # incomparable units (for example USD vs percent)
    values = {cid: v for cid, (v, _) in normed.items()}
    low, high = min(values.values()), max(values.values())
    if low == high:
        return None
    denominator = min(abs(low), abs(high))
    pct = 1000.0 if denominator == 0 else min((high - low) / denominator * 100.0, 1000.0)
    if pct <= CONFLICT_THRESHOLD_PCT:
        return None
    unit = next(iter(normed.values()))[1]
    return ConflictFlag(
        metric_name=group.metric_name,
        period=group.period,
        unit=unit,
        claim_ids=list(values),
        values=values,
        pct_difference=round(pct, 2),
        severity="high" if pct > 25 else "medium" if pct > 10 else "low",
        explanation=(f"{group.metric_name} ({group.period or 'period n/a'}) differs by {pct:.1f}% across sources: "
                     + "; ".join(f"{by_id[c].source_url} = {v:,.2f} {unit}" for c, v in values.items())),
    )


async def cross_check_claims(
    goal: SubGoal, ticker: str, run_id: str, claims: list[VerifiedClaim], events: list[dict[str, Any]]
) -> list[ConflictFlag]:
    """Flag numeric claims for the same metric/period whose values disagree by >5%."""
    started = now()
    numeric = [c for c in claims if c.numeric_value() is not None]
    if len(numeric) < 2:
        events.append(make_event(node="quant_executor", run_id=run_id, started_at=started,
                                 detail={"goal_id": goal.goal_id, "skipped": "fewer than two numeric claims"}))
        return []
    payload = [{"claim_id": c.claim_id, "metric_name": c.metric_name, "period": c.period,
                "value": c.value, "unit": c.unit, "source_type": c.source_type, "source_url": c.source_url}
               for c in numeric]
    grouping = await groq_client.call_structured(
        model=MODEL_LARGE,
        system=render(QUANT_SYSTEM, ticker=ticker),
        user=json.dumps({"claims": payload}, ensure_ascii=False),
        schema=ClaimGrouping,
        tool_name="group_numeric_claims",
        tool_description="Group claim ids that describe the same metric and period.",
        run_id=run_id,
        node="quant_executor",
        events=events,
        max_tokens=2000,
    )
    by_id = {c.claim_id: c for c in numeric}
    flags = [f for g in grouping.groups if (f := compare_group(g, by_id)) is not None]
    events.append(make_event(node="quant_executor", run_id=run_id, started_at=started,
                             detail={"goal_id": goal.goal_id, "groups": len(grouping.groups), "conflicts": len(flags)}))
    return flags


if __name__ == "__main__":
    from agents.mock_data import MOCK_REQUEST

    async def _demo() -> None:
        mk = lambda cid, url, st, val, unit: VerifiedClaim(  # noqa: E731
            claim_id=cid, metric_name="revenue", value=val, unit=unit, period="FY2025",
            source_type=st, source_url=url, confidence=0.9)
        claims = [mk("g1-c1", "https://api.examplefin.test/acme", "financial_api", 12500, "USD millions"),
                  mk("g2-c1", "https://www.sec.gov/acme-10k", "sec_filing", 11.9, "USD billions")]
        goal = SubGoal(goal_id="g4", description="Cross-check revenue", agent_type="quant", depends_on=["g1", "g2"])
        flags = await cross_check_claims(goal, MOCK_REQUEST.ticker, MOCK_REQUEST.run_id, claims, [])
        print(json.dumps([f.model_dump(mode="json") for f in flags], indent=2))

    asyncio.run(_demo())
