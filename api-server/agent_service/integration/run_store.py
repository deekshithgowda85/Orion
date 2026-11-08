"""Synchronous Neon writer for Layer 1 (Temporal activities) / Layer 2.

COPY INTO your worker project (needs `pip install "psycopg[binary]"` and NEON_DATABASE_URL).
Temporal activities may be sync or async; these functions are plain sync and short, so call them
from a sync activity or wrap with `await asyncio.to_thread(...)` from an async one.

These write the same tables the API reads (workflow_runs, citations), so /status, /report and
/history reflect the run. All functions raise on DB errors so Temporal can retry the activity.
"""
from __future__ import annotations

import os
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


def _conn() -> psycopg.Connection:
    return psycopg.connect(os.environ["NEON_DATABASE_URL"], autocommit=True, prepare_threshold=None, connect_timeout=10)


def mark_running(run_id: str) -> None:
    with _conn() as c:
        c.execute("UPDATE workflow_runs SET status='running' WHERE id=%s AND status='queued'", (run_id,))


def update_step(run_id: str, step: str, progress_pct: int, trace: dict[str, Any] | None = None) -> None:
    with _conn() as c:
        c.execute(
            """UPDATE workflow_runs
                  SET current_step=%s, progress_pct=GREATEST(progress_pct,%s),
                      status=CASE WHEN status='queued' THEN 'running' ELSE status END,
                      trace_log_jsonb = CASE WHEN %s::jsonb IS NOT NULL
                                        THEN trace_log_jsonb || jsonb_build_array(%s::jsonb) ELSE trace_log_jsonb END
                WHERE id=%s""",
            (step, max(0, min(100, progress_pct)), Jsonb(trace) if trace else None, Jsonb(trace) if trace else None, run_id),
        )


def save_citation(run_id: str, *, source_url=None, source_type=None, metric_name=None, value=None,
                  period=None, confidence=None, raw_snippet=None) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO citations (run_id, source_url, source_type, metric_name, value, period, confidence, raw_snippet)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (run_id, source_url, source_type, metric_name, None if value is None else str(value), period, confidence, raw_snippet),
        )


def save_report(run_id: str, report: dict[str, Any]) -> None:
    """Store the final report and mark the run completed. Call BEFORE publish_report_ready()."""
    with _conn() as c:
        c.execute(
            "UPDATE workflow_runs SET report_jsonb=%s, status='completed', progress_pct=100, completed_at=now() WHERE id=%s",
            (Jsonb(report), run_id),
        )


def mark_failed(run_id: str, error: str) -> None:
    with _conn() as c:
        c.execute(
            """UPDATE workflow_runs
                  SET status='failed', completed_at=now(),
                      trace_log_jsonb = trace_log_jsonb || jsonb_build_array(jsonb_build_object('error', %s::text, 'at', now()))
                WHERE id=%s""",
            (error[:1000], run_id),
        )
