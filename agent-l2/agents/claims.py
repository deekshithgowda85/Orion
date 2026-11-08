"""Pure helpers for merging claims and building the citation catalogue."""
from urllib.parse import urlparse

from models.workflow_models import CitationRef, ConflictFlag, NewsSummary, VerifiedClaim


def _claim_key(claim: VerifiedClaim) -> tuple[str, str, str, str]:
    """Identity of a claim for de-duplication."""
    return (claim.metric_name.lower(), (claim.period or "").lower(), claim.source_url, str(claim.value))


def merge_claims(existing: list[VerifiedClaim], new: list[VerifiedClaim]) -> list[VerifiedClaim]:
    """Merge ``new`` into ``existing``; duplicates keep the lower (more conservative) confidence."""
    merged: dict[tuple[str, str, str, str], VerifiedClaim] = {_claim_key(c): c for c in existing}
    for claim in new:
        key = _claim_key(claim)
        if key in merged:
            old = merged[key]
            merged[key] = old if old.confidence <= claim.confidence else claim.model_copy(update={"claim_id": old.claim_id})
        else:
            merged[key] = claim
    return list(merged.values())


def merge_flags(existing: list[ConflictFlag], new: list[ConflictFlag]) -> list[ConflictFlag]:
    """Replace flags for the same metric/period with the newest one."""
    merged = {(f.metric_name.lower(), (f.period or "").lower()): f for f in existing}
    for flag in new:
        merged[(flag.metric_name.lower(), (flag.period or "").lower())] = flag
    return list(merged.values())


def host_of(url: str) -> str:
    """Return the host part of a URL (used as a fallback title/publisher)."""
    return urlparse(url).netloc or url


def build_citations(claims: list[VerifiedClaim], news: list[NewsSummary]) -> list[CitationRef]:
    """Number every distinct source 1..n in order of first appearance.

    ``citation_id`` is the string form of the number used inline as ``[n]``.
    """
    seen: dict[str, CitationRef] = {}

    def add(url: str, title: str | None, excerpt: str | None, goal_id: str | None) -> None:
        if url and url not in seen:
            seen[url] = CitationRef(
                citation_id=str(len(seen) + 1),
                source_url=url,
                title=title or host_of(url),
                publisher=host_of(url),
                excerpt=excerpt,
                task_id=goal_id,
            )

    for claim in claims:
        add(claim.source_url, claim.source_title, claim.statement, claim.goal_id)
    for summary in news:
        for event in summary.key_events:
            if event.source_url:
                add(event.source_url, None, event.description, summary.goal_id)
        for url in summary.source_urls:
            add(url, None, None, summary.goal_id)
    return list(seen.values())
