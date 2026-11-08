"""Environment-driven configuration for Layer 3."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass


class ConfigError(RuntimeError):
    """Raised when required environment variables are missing or malformed."""


REQUIRED_ENV = (
    "POLYGON_API_KEY",
    "E2B_API_KEY",
    "SEC_EDGAR_USER_AGENT",
    "REDIS_URL",
    "NEON_DATABASE_URL",
    "OPENAI_API_KEY",
)


@dataclass(frozen=True)
class Settings:
    polygon_api_key: str
    e2b_api_key: str
    sec_user_agent: str
    redis_url: str
    neon_database_url: str
    openai_api_key: str
    firecrawl_api_key: str | None = None
    llama_cloud_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"

    @classmethod
    def from_env(cls) -> "Settings":
        missing = [n for n in REQUIRED_ENV if not os.environ.get(n)]
        if missing:
            raise ConfigError("Missing required environment variables: " + ", ".join(missing))
        ua = os.environ["SEC_EDGAR_USER_AGENT"].strip().strip('"')
        if "@" not in ua:
            raise ConfigError('SEC_EDGAR_USER_AGENT must look like "YourName yourname@example.com"')
        return cls(
            polygon_api_key=os.environ["POLYGON_API_KEY"],
            e2b_api_key=os.environ["E2B_API_KEY"],
            sec_user_agent=ua,
            redis_url=os.environ["REDIS_URL"],
            neon_database_url=os.environ["NEON_DATABASE_URL"],
            openai_api_key=os.environ["OPENAI_API_KEY"],
            firecrawl_api_key=os.environ.get("FIRECRAWL_API_KEY") or None,
            llama_cloud_api_key=os.environ.get("LLAMA_CLOUD_API_KEY") or None,
            embedding_model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        )
