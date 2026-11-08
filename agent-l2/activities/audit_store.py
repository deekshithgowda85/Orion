"""Neon (Postgres) persistence for audit traces: table ``workflow_traces``."""
import logging
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import asyncpg

logger = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS workflow_traces (
    audit_id           UUID PRIMARY KEY,
    tenant_id          TEXT NOT NULL,
    run_id             TEXT NOT NULL,
    ticker             TEXT NOT NULL,
    workflow_type      TEXT NOT NULL,
    record_count       INTEGER NOT NULL,
    overall_confidence DOUBLE PRECISION,
    jsonl              TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, run_id)
);
CREATE INDEX IF NOT EXISTS idx_workflow_traces_tenant_created ON workflow_traces (tenant_id, created_at DESC);
"""

UPSERT = """
INSERT INTO workflow_traces (audit_id, tenant_id, run_id, ticker, workflow_type, record_count, overall_confidence, jsonl)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (audit_id) DO UPDATE SET
    record_count = EXCLUDED.record_count,
    overall_confidence = EXCLUDED.overall_confidence,
    jsonl = EXCLUDED.jsonl,
    created_at = now()
"""


def clean_dsn(url: str) -> str:
    """Drop libpq-only query params (Neon adds ``channel_binding``) that asyncpg rejects."""
    parts = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in {"channel_binding"}]
    return urlunparse(parts._replace(query=urlencode(query)))


async def store_trace(*, audit_id: str, tenant_id: str, run_id: str, ticker: str, workflow_type: str,
                      record_count: int, confidence: float, jsonl: str) -> str:
    """Write the .jsonl trace to Neon (idempotent upsert); returns ``"neon"`` or ``"local_file"``.

    If ``NEON_DATABASE_URL`` is not configured, the trace is written to
    ``AUDIT_LOCAL_DIR`` (default ``./traces``) so local development still works.
    """
    dsn = os.getenv("NEON_DATABASE_URL")
    if not dsn:
        directory = Path(os.getenv("AUDIT_LOCAL_DIR", "traces")) / tenant_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{run_id}.jsonl").write_text(jsonl, encoding="utf-8")
        logger.warning("NEON_DATABASE_URL not set; trace written to %s", directory)
        return "local_file"
    conn = await asyncpg.connect(clean_dsn(dsn), statement_cache_size=0, timeout=15)  # pgbouncer-safe
    try:
        await conn.execute(DDL)
        await conn.execute(UPSERT, audit_id, tenant_id, run_id, ticker, workflow_type, record_count, confidence, jsonl)
    finally:
        await conn.close()
    return "neon"
