"""Async Postgres access layer for Neon.

Note: psycopg2 has no native asyncio support, so this uses psycopg 3
(`psycopg[pool]`), the maintained successor with the same libpq driver and an
AsyncConnectionPool.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

log = logging.getLogger("db")
_pool: Optional[AsyncConnectionPool] = None


async def init_pool(dsn: str, min_size: int = 1, max_size: int = 10, timeout: float = 10.0) -> AsyncConnectionPool:
    global _pool
    # prepare_threshold=None: safe behind Neon's pgbouncer (-pooler) endpoints.
    # check=: Neon suspends idle computes, so validate connections before handing them out.
    _pool = AsyncConnectionPool(
        conninfo=dsn,
        min_size=min_size,
        max_size=max_size,
        timeout=timeout,
        max_idle=240,
        check=AsyncConnectionPool.check_connection,
        kwargs={"row_factory": dict_row, "autocommit": True, "prepare_threshold": None},
        open=False,
    )
    try:
        await _pool.open(wait=True, timeout=min(timeout * 2, 30))
    except Exception:
        # Leave the pool retrying in the background; requests return 503 until the DB is reachable.
        log.exception("could not connect to the database at startup; will keep retrying")
        await _pool.open(wait=False)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised")
    return _pool


async def ping() -> bool:
    async with pool().connection() as conn:
        await conn.execute("SELECT 1")
    return True


# ------------------------------------------------------------------ tenants
async def get_or_create_tenant(clerk_org_id: str, name: str | None = None) -> dict[str, Any]:
    async with pool().connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO tenants (name, clerk_org_id)
            VALUES (%s, %s)
            ON CONFLICT (clerk_org_id) DO UPDATE SET clerk_org_id = EXCLUDED.clerk_org_id
            RETURNING id, name, clerk_org_id, plan_tier, created_at
            """,
            (name or clerk_org_id, clerk_org_id),
        )
        return await cur.fetchone()  # type: ignore[return-value]


# --------------------------------------------------------------------- runs
async def create_run(
    *,
    run_id: UUID,
    tenant_id: UUID,
    user_id: str | None,
    ticker: str,
    query: str,
    workflow_type: str,
    priority: str = "normal",
    quarter: str | None = None,
) -> dict[str, Any]:
    async with pool().connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO workflow_runs (id, tenant_id, user_id, ticker, quarter, query, workflow_type, priority, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'queued')
            RETURNING *
            """,
            (run_id, tenant_id, user_id, ticker, quarter, query, workflow_type, priority),
        )
        return await cur.fetchone()  # type: ignore[return-value]


async def update_run_status(
    run_id: UUID, tenant_id: UUID, status: str, *, error: str | None = None
) -> None:
    terminal = status in ("completed", "failed", "cancelled")
    async with pool().connection() as conn:
        await conn.execute(
            """
            UPDATE workflow_runs
               SET status = %s,
                   completed_at = CASE WHEN %s THEN now() ELSE completed_at END,
                   progress_pct = CASE WHEN %s = 'completed' THEN 100 ELSE progress_pct END,
                   trace_log_jsonb = CASE WHEN %s::text IS NOT NULL
                       THEN trace_log_jsonb || jsonb_build_array(jsonb_build_object('error', %s::text, 'at', now()))
                       ELSE trace_log_jsonb END
             WHERE id = %s AND tenant_id = %s
            """,
            (status, terminal, status, error, error, run_id, tenant_id),
        )


async def update_run_step(
    run_id: UUID,
    tenant_id: UUID,
    current_step: str,
    progress_pct: int,
    trace_entry: dict[str, Any] | None = None,
) -> None:
    async with pool().connection() as conn:
        await conn.execute(
            """
            UPDATE workflow_runs
               SET current_step = %s,
                   progress_pct = GREATEST(progress_pct, %s),
                   status = CASE WHEN status = 'queued' THEN 'running' ELSE status END,
                   trace_log_jsonb = CASE WHEN %s::jsonb IS NOT NULL
                       THEN trace_log_jsonb || jsonb_build_array(%s::jsonb)
                       ELSE trace_log_jsonb END
             WHERE id = %s AND tenant_id = %s
            """,
            (
                current_step,
                max(0, min(100, progress_pct)),
                Jsonb(trace_entry) if trace_entry else None,
                Jsonb(trace_entry) if trace_entry else None,
                run_id,
                tenant_id,
            ),
        )


async def touch_run_step_by_id(run_id: UUID, current_step: str | None, progress_pct: int | None) -> None:
    """Used by the Redis event sink (no tenant context; run ids are unguessable UUIDs set by us)."""
    async with pool().connection() as conn:
        await conn.execute(
            """
            UPDATE workflow_runs
               SET current_step = COALESCE(%s, current_step),
                   progress_pct = GREATEST(progress_pct, COALESCE(%s, progress_pct)),
                   status = CASE WHEN status = 'queued' THEN 'running' ELSE status END
             WHERE id = %s AND status IN ('queued', 'running')
            """,
            (current_step, progress_pct, run_id),
        )


async def get_run_status_by_id(run_id: UUID, tenant_id: UUID) -> Optional[str]:
    async with pool().connection() as conn:
        cur = await conn.execute(
            "SELECT status FROM workflow_runs WHERE id = %s AND tenant_id = %s", (run_id, tenant_id)
        )
        row = await cur.fetchone()
        return row["status"] if row else None


async def save_report(run_id: UUID, tenant_id: UUID, report: dict[str, Any]) -> None:
    async with pool().connection() as conn:
        await conn.execute(
            """
            UPDATE workflow_runs
               SET report_jsonb = %s, status = 'completed', progress_pct = 100, completed_at = now()
             WHERE id = %s AND tenant_id = %s
            """,
            (Jsonb(report), run_id, tenant_id),
        )


async def get_run(run_id: UUID, tenant_id: UUID) -> Optional[dict[str, Any]]:
    async with pool().connection() as conn:
        cur = await conn.execute(
            "SELECT * FROM workflow_runs WHERE id = %s AND tenant_id = %s", (run_id, tenant_id)
        )
        return await cur.fetchone()


async def list_runs_by_tenant(
    tenant_id: UUID,
    *,
    ticker: str | None = None,
    workflow_type: str | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    where = ["tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if ticker:
        where.append("ticker = %s")
        params.append(ticker.upper())
    if workflow_type:
        where.append("workflow_type = %s")
        params.append(workflow_type)
    if status:
        where.append("status = %s")
        params.append(status)
    if date_from:
        where.append("started_at >= %s")
        params.append(date_from)
    if date_to:
        where.append("started_at <= %s")
        params.append(date_to)
    clause = " AND ".join(where)
    offset = (page - 1) * page_size
    async with pool().connection() as conn:
        cur = await conn.execute(f"SELECT count(*) AS n FROM workflow_runs WHERE {clause}", params)
        total = (await cur.fetchone())["n"]  # type: ignore[index]
        cur = await conn.execute(
            f"""
            SELECT id, tenant_id, ticker, quarter, query, workflow_type, status, current_step,
                   progress_pct, started_at, completed_at
              FROM workflow_runs WHERE {clause}
             ORDER BY started_at DESC LIMIT %s OFFSET %s
            """,
            [*params, page_size, offset],
        )
        rows = await cur.fetchall()
    return rows, total


# ---------------------------------------------------------------- citations
async def save_citation(
    run_id: UUID,
    *,
    source_url: str | None,
    source_type: str | None,
    metric_name: str | None,
    value: str | None,
    period: str | None,
    confidence: float | None,
    raw_snippet: str | None,
) -> dict[str, Any]:
    async with pool().connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO citations (run_id, source_url, source_type, metric_name, value, period, confidence, raw_snippet)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (run_id, source_url, source_type, metric_name, value, period, confidence, raw_snippet),
        )
        return await cur.fetchone()  # type: ignore[return-value]


async def list_citations_by_run(run_id: UUID) -> list[dict[str, Any]]:
    async with pool().connection() as conn:
        cur = await conn.execute("SELECT * FROM citations WHERE run_id = %s ORDER BY metric_name", (run_id,))
        return await cur.fetchall()


# ---------------------------------------------------------------- schedules
async def create_schedule(
    tenant_id: UUID,
    inngest_schedule_id: str | None,
    ticker: str,
    workflow_type: str,
    cron_expr: str,
    query: str | None = None,
) -> dict[str, Any]:
    async with pool().connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO workflow_schedules (tenant_id, inngest_schedule_id, ticker, workflow_type, cron_expr, query)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (tenant_id, inngest_schedule_id, ticker.upper(), workflow_type, cron_expr, query),
        )
        return await cur.fetchone()  # type: ignore[return-value]


async def get_schedule(schedule_id: UUID, tenant_id: UUID) -> Optional[dict[str, Any]]:
    async with pool().connection() as conn:
        cur = await conn.execute(
            "SELECT * FROM workflow_schedules WHERE id = %s AND tenant_id = %s", (schedule_id, tenant_id)
        )
        return await cur.fetchone()


async def list_schedules(tenant_id: UUID) -> list[dict[str, Any]]:
    async with pool().connection() as conn:
        cur = await conn.execute(
            "SELECT * FROM workflow_schedules WHERE tenant_id = %s AND active ORDER BY created_at DESC",
            (tenant_id,),
        )
        return await cur.fetchall()


async def deactivate_schedule(schedule_id: UUID, tenant_id: UUID) -> bool:
    async with pool().connection() as conn:
        cur = await conn.execute(
            "UPDATE workflow_schedules SET active = FALSE WHERE id = %s AND tenant_id = %s AND active",
            (schedule_id, tenant_id),
        )
        return cur.rowcount > 0


async def list_active_schedules_all() -> list[dict[str, Any]]:
    async with pool().connection() as conn:
        cur = await conn.execute("SELECT * FROM workflow_schedules WHERE active")
        return await cur.fetchall()


async def mark_schedule_ran(schedule_id: UUID, when: datetime) -> None:
    async with pool().connection() as conn:
        await conn.execute("UPDATE workflow_schedules SET last_run_at = %s WHERE id = %s", (when, schedule_id))


def _json_default(o: Any) -> Any:  # pragma: no cover
    return str(o)


def dumps(o: Any) -> str:  # pragma: no cover
    return json.dumps(o, default=_json_default)
