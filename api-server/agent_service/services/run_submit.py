"""Shared "start a research run" logic used by POST /research/submit and the schedule runner."""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID, uuid4

from db import queries
from services import temporal_service

log = logging.getLogger("runs")


async def submit_run(
    app: Any,
    *,
    tenant_id: UUID,
    user_id: str,
    ticker: str,
    quarter: Optional[str],
    query: str,
    workflow_type: str,
    priority: str,
) -> UUID:
    """Raises temporal_service.TemporalUnavailable (-> 503) BEFORE any DB row is written if Temporal is
    down, so a dead workflow engine never leaves 'queued' ghost runs. If the start call itself fails
    after the row exists, the row is marked failed."""
    client = await temporal_service.get_client(app)
    run_id = uuid4()
    await queries.create_run(
        run_id=run_id, tenant_id=tenant_id, user_id=user_id, ticker=ticker, quarter=quarter,
        query=query, workflow_type=workflow_type, priority=priority,
    )
    try:
        await temporal_service.start_research_workflow(
            client, run_id=str(run_id), tenant_id=str(tenant_id), user_id=user_id,
            ticker=ticker, quarter=quarter, query=query, workflow_type=workflow_type, priority=priority,
        )
    except Exception as exc:
        log.exception("failed to start temporal workflow", extra={"run_id": str(run_id)})
        try:
            await queries.update_run_status(run_id, tenant_id, "failed", error=f"start failed: {exc}"[:500])
        except Exception:
            log.exception("could not mark run failed")
        raise temporal_service.TemporalUnavailable(
            "Temporal rejected the workflow start (is the worker registered as "
            f"'{temporal_service.get_settings().temporal_workflow_name}' on queue "
            f"'{temporal_service.get_settings().temporal_task_queue}'?)"
        ) from exc
    return run_id
