"""Central configuration and shared constants for Layer 1."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

TASK_QUEUE: str = "market-research-queue"
WORKFLOW_EXECUTION_TIMEOUT: timedelta = timedelta(minutes=30)
APPROVAL_TIMEOUT: timedelta = timedelta(minutes=5)

EVENT_QUERY_SUBMITTED: str = "market-research/query.submitted"
EVENT_DAILY_SCAN: str = "market-research/portfolio.daily-scan"
# 07:00 UTC, Monday-Friday.
DAILY_SCAN_CRON: str = "TZ=UTC 0 7 * * 1-5"


def workflow_id_for(tenant_id: str, run_id: str) -> str:
    """Return the deterministic Temporal workflow ID for a research run.

    A deterministic ID makes starts idempotent: re-delivering the same
    Inngest event cannot create a duplicate workflow.
    """
    return f"research-{tenant_id}-{run_id}"


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    temporal_host: str
    temporal_namespace: str
    inngest_event_key: str | None
    inngest_signing_key: str | None
    inngest_dev: bool
    neon_database_url: str | None
    redis_url: str
    daily_scan_tickers: tuple[str, ...]
    daily_scan_tenant_id: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from the process environment."""
        tickers = os.getenv("DAILY_SCAN_TICKERS", "")
        return cls(
            temporal_host=os.getenv("TEMPORAL_HOST", "localhost:7233"),
            temporal_namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
            inngest_event_key=os.getenv("INNGEST_EVENT_KEY") or None,
            inngest_signing_key=os.getenv("INNGEST_SIGNING_KEY") or None,
            inngest_dev=os.getenv("INNGEST_DEV", "1") in {"1", "true", "True"},
            neon_database_url=os.getenv("NEON_DATABASE_URL") or None,
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            daily_scan_tickers=tuple(t.strip().upper() for t in tickers.split(",") if t.strip()),
            daily_scan_tenant_id=os.getenv("DAILY_SCAN_TENANT_ID", "default-tenant"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process-wide :class:`Settings`."""
    return Settings.from_env()
