"""FastAPI agent service entrypoint. Run from inside the agent_service folder:  uvicorn main:app --port 8000"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis_async
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg import OperationalError
from psycopg_pool import PoolTimeout

from config import get_settings
from db import queries
from logging_config import setup_logging
from middleware.auth import ClerkAuthMiddleware
from middleware.request_context import RequestContextMiddleware
from routes import internal, research, workflows
from services import event_sink, temporal_service

log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    app.state.redis = redis_async.Redis.from_url(
        settings.redis_url, decode_responses=True, socket_connect_timeout=5, health_check_interval=30
    )
    try:
        await app.state.redis.ping()
    except Exception:
        log.error("Redis not reachable at %s - SSE streaming and tenant caching degraded", settings.redis_url)
    await queries.init_pool(
        settings.neon_database_url, settings.db_pool_min, settings.db_pool_max, settings.db_pool_timeout
    )
    try:
        app.state.temporal = await temporal_service.connect()
    except Exception:
        # Stay up: history/status/report still work. Submissions retry the connection and return 503 until it works.
        log.error("Temporal not reachable at %s - submissions will return 503", settings.temporal_host)
        app.state.temporal = None
    sink = asyncio.create_task(event_sink.run_event_sink(app), name="event-sink")
    log.info("agent service started")
    try:
        yield
    finally:
        sink.cancel()
        try:
            await sink
        except (asyncio.CancelledError, Exception):
            pass
        await queries.close_pool()
        await app.state.redis.aclose()
        log.info("agent service stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Market Research Agent Service", version="1.1.0", lifespan=lifespan)

    # Starlette runs middleware in reverse order of registration: CORS outermost, then
    # request-context, then auth (so auth failures are logged and carry X-Request-ID).
    app.add_middleware(ClerkAuthMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.bff_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Tenant-ID", "X-User-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.exception_handler(OperationalError)
    @app.exception_handler(PoolTimeout)
    async def db_unavailable(_: Request, exc: Exception) -> JSONResponse:
        log.error("database unavailable: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Database (Neon) unavailable, try again shortly"})

    @app.exception_handler(temporal_service.TemporalUnavailable)
    async def temporal_unavailable(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": f"Workflow engine unavailable: {exc}"})

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        db_ok = redis_ok = False
        try:
            db_ok = await asyncio.wait_for(queries.ping(), timeout=3)
        except Exception:
            pass
        try:
            redis_ok = bool(await asyncio.wait_for(app.state.redis.ping(), timeout=3))
        except Exception:
            pass
        temporal_ok = await temporal_service.check_health(getattr(app.state, "temporal", None))
        ok = db_ok and redis_ok and temporal_ok
        return {"status": "ok" if ok else "degraded", "neon": db_ok, "redis": redis_ok, "temporal": temporal_ok}

    app.include_router(research.router)
    app.include_router(workflows.router)
    app.include_router(internal.router)
    return app


app = create_app()
