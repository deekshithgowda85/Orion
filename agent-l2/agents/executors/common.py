"""Shared helpers for the extraction executors."""
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from agents.settings import MAX_RAW_CHARS
from models.workflow_models import SourceType, VerifiedClaim


class ClaimDraft(BaseModel):
    """LLM-facing claim (market data)."""

    metric_name: str
    value: float | str | None = None
    unit: str | None = None
    period: str | None = None
    source_url: str
    confidence: float = Field(ge=0.0, le=1.0)
    statement: str | None = Field(default=None, description="One-sentence plain-English claim")


class ClaimExtraction(BaseModel):
    """Tool schema for extract_market_claims."""

    claims: list[ClaimDraft] = Field(default_factory=list, max_length=60)


class FilingClaimDraft(ClaimDraft):
    """LLM-facing claim (filings / transcripts)."""

    page_ref: str | None = None
    filing_type: Literal["10-K", "10-Q", "8-K", "transcript", "other"] = "other"
    fiscal_period: str | None = None


class FilingExtraction(BaseModel):
    """Tool schema for extract_filing_claims."""

    claims: list[FilingClaimDraft] = Field(default_factory=list, max_length=60)


def has_data(raw: dict[str, Any] | None) -> bool:
    """True when a tool payload has both content and at least one source URL."""
    return bool(raw and raw.get("content") and raw.get("sources"))


def render_raw(raw: dict[str, Any]) -> tuple[str, dict[str, str | None]]:
    """Render a tool payload for prompting.

    Returns:
        (prompt text, mapping of allowed source url -> title)
    """
    titles = {s["url"]: s.get("title") for s in raw.get("sources", []) if s.get("url")}
    content = raw.get("content")
    body = content if isinstance(content, str) else json.dumps(content, default=str, ensure_ascii=False)
    truncated = len(body) > MAX_RAW_CHARS
    source_lines = "\n".join(f"- {url} ({title or 'untitled'})" for url, title in titles.items())
    text = (
        f"<sources>\n{source_lines}\n</sources>\n"
        f"<source_data>\n{body[:MAX_RAW_CHARS]}\n</source_data>"
        + ("\n(Source data was truncated.)" if truncated else "")
    )
    return text, titles


def to_claims(
    drafts: list[ClaimDraft],
    *,
    goal_id: str,
    titles: dict[str, str | None],
    model: str,
    source_type: SourceType | None = None,
) -> tuple[list[VerifiedClaim], int]:
    """Convert LLM drafts to :class:`VerifiedClaim`, dropping claims with unknown source URLs.

    Returns:
        (claims, number_dropped)
    """
    claims: list[VerifiedClaim] = []
    dropped = 0
    for draft in drafts:
        if draft.source_url not in titles:
            dropped += 1
            continue
        stype: SourceType = source_type or "other"
        extra: dict[str, Any] = {}
        if isinstance(draft, FilingClaimDraft):
            stype = "transcript" if draft.filing_type == "transcript" else (
                "sec_filing" if draft.filing_type in {"10-K", "10-Q", "8-K"} else "other")
            extra = {"page_ref": draft.page_ref, "filing_type": draft.filing_type, "fiscal_period": draft.fiscal_period}
        claims.append(VerifiedClaim(
            claim_id=f"{goal_id}-c{len(claims) + 1}",
            goal_id=goal_id,
            statement=draft.statement,
            metric_name=draft.metric_name,
            value=draft.value,
            unit=draft.unit,
            period=draft.period,
            source_type=stype,
            source_url=draft.source_url,
            source_title=titles[draft.source_url],
            confidence=draft.confidence,
            extracted_by=model,
            **extra,
        ))
    return claims, dropped
