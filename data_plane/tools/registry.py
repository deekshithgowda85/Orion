"""ToolRegistry singleton: builds every tool client once at worker startup."""
from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis

from .common import get_logger, log_event
from .config import Settings

log = get_logger("registry")


class ToolRegistry:
    _instance: "ToolRegistry | None" = None
    _init_lock = asyncio.Lock()

    def __init__(self, settings: Settings) -> None:
        # Imported here so `import tools.registry` stays light and avoids import cycles.
        from .market_data import MarketDataTool
        from .quant_sandbox import QuantSandboxTool
        from .scraper import ScraperTool
        from .scratchpad import Scratchpad
        from .sec_filings import SECFilingsTool
        from .vector_store import VectorStore

        self.settings = settings
        # decode_responses=False: scratchpad stores gzip bytes; market cache decodes itself.
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=False)
        self._scratchpad_cls = Scratchpad
        self._market = MarketDataTool(settings.polygon_api_key, self._redis)
        self._filings = SECFilingsTool(settings.sec_user_agent, settings.llama_cloud_api_key)
        self._scraper = ScraperTool(settings.firecrawl_api_key)
        self._sandbox = QuantSandboxTool(settings.e2b_api_key)
        self._vectors = VectorStore(settings.neon_database_url, settings.openai_api_key,
                                    settings.embedding_model)

    # ---- lifecycle
    @classmethod
    async def initialize(cls, settings: Settings | None = None) -> "ToolRegistry":
        """Idempotent. Call once at Temporal worker startup."""
        async with cls._init_lock:
            if cls._instance is None:
                inst = cls(settings or Settings.from_env())
                await inst._vectors.ensure_schema()
                await inst._redis.ping()
                cls._instance = inst
                log_event(log, logging.INFO, "tool_registry_initialized")
            return cls._instance

    @classmethod
    def instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            raise RuntimeError("ToolRegistry.initialize() has not been called")
        return cls._instance

    @classmethod
    async def shutdown(cls) -> None:
        inst = cls._instance
        if inst is None:
            return
        for closer in (inst._filings.aclose(), inst._scraper.aclose(), inst._vectors.close(),
                       inst._redis.aclose()):
            try:
                await closer
            except Exception as exc:  # noqa: BLE001
                log_event(log, logging.ERROR, "registry_shutdown_error", error=repr(exc))
        cls._instance = None

    # ---- accessors
    def get_market_tool(self):
        return self._market

    def get_filings_tool(self):
        return self._filings

    def get_scraper_tool(self):
        return self._scraper

    def get_sandbox_tool(self):
        return self._sandbox

    def get_vector_store(self):
        return self._vectors

    def get_scratchpad(self, run_id: str):
        """Per-run Redis scratchpad (key prefix `scratchpad:{run_id}:`)."""
        return self._scratchpad_cls(self._redis, run_id)

    def get_redis(self):
        return self._redis
