"""Central configuration loaded from environment variables / .env file."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- required -------------------------------------------------------------
    neon_database_url: str
    clerk_jwks_url: str

    # --- Layer 1 (Temporal) ---------------------------------------------------
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "market-research"
    temporal_workflow_name: str = "MarketResearchWorkflow"
    temporal_connect_timeout: float = 10.0
    workflow_execution_timeout_seconds: int = 3600

    # --- Redis ----------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # --- Clerk ----------------------------------------------------------------
    clerk_secret_key: str = ""  # not used for JWT verification (JWKS is); reserved for Clerk API calls
    clerk_issuer: str = ""  # recommended: enforces the `iss` claim

    # --- BFF / CORS -----------------------------------------------------------
    bff_origin: str = "http://localhost:3001"

    # --- Scheduling (optional) ------------------------------------------------
    inngest_event_key: str = ""  # enables Inngest Event API notifications
    inngest_event_url: str = "https://inn.gs/e"
    internal_api_key: str = ""  # shared secret for POST /internal/schedules/run-due

    # --- behaviour ------------------------------------------------------------
    default_quarter: Optional[str] = None  # used when a submit request omits `quarter`
    sse_timeout_seconds: int = 35 * 60
    sse_status_poll_seconds: float = 5.0
    db_pool_min: int = 1
    db_pool_max: int = 10
    db_pool_timeout: float = 10.0
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        missing = sorted({str(e["loc"][0]).upper() for e in exc.errors() if e["type"] == "missing"})
        other = [f"{str(e['loc'][0]).upper()}: {e['msg']}" for e in exc.errors() if e["type"] != "missing"]
        lines = ["agent_service cannot start: invalid configuration."]
        if missing:
            lines.append("  Missing required environment variables: " + ", ".join(missing))
        lines += [f"  Invalid: {o}" for o in other]
        lines.append("  Copy .env.example to .env and fill the values (run uvicorn from the agent_service folder).")
        raise SystemExit("\n".join(lines)) from None
