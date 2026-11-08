"""Agent-level trace event helper (plain dicts, JSON serialisable)."""
from datetime import datetime, timezone
from typing import Any


def now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


def make_event(
    *,
    node: str,
    run_id: str,
    started_at: datetime,
    status: str = "success",
    event_type: str = "node",
    model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    attempts: int = 1,
    error: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one trace event dict (matches ``AgentTraceEvent``)."""
    return {
        "event_type": event_type,
        "node": node,
        "run_id": run_id,
        "model": model,
        "started_at": started_at.isoformat(),
        "completed_at": now().isoformat(),
        "status": status,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "attempts": attempts,
        "error": error,
        "detail": detail or {},
    }
