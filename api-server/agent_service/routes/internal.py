"""Internal endpoints (not behind Clerk). Protected by the X-Internal-Key shared secret.

POST /internal/schedules/run-due   - call once a minute from Inngest / cron / Task Scheduler.
"""
from __future__ import annotations

import hmac
import logging
from datetime import datetime, timezone

from croniter import croniter
from fastapi import APIRouter, Header, HTTPException, Request

from config import get_settings
from db import queries
from services import run_submit, temporal_service

log = logging.getLogger("internal")
router = APIRouter(prefix="/internal", tags=["internal"])


def _check_key(provided: str | None) -> None:
    expected = get_settings().internal_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="Internal endpoints disabled: set INTERNAL_API_KEY")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid internal key")


@router.post("/schedules/run-due")
async def run_due_schedules(request: Request, x_internal_key: str | None = Header(None)) -> dict:
    _check_key(x_internal_key)
    now = datetime.now(timezone.utc)
    fired: list[str] = []
    errors: list[dict] = []
    for sched in await queries.list_active_schedules_all():
        base = sched["last_run_at"] or sched["created_at"]
        try:
            next_fire = croniter(sched["cron_expr"], base).get_next(datetime)
        except Exception:
            errors.append({"schedule_id": str(sched["id"]), "error": "invalid cron_expr"})
            continue
        if next_fire > now:
            continue
        try:
            await run_submit.submit_run(
                request.app,
                tenant_id=sched["tenant_id"],
                user_id="scheduler",
                ticker=sched["ticker"],
                quarter=get_settings().default_quarter or None,
                query=sched.get("query") or "Scheduled research run",
                workflow_type=sched["workflow_type"],
                priority="low",
            )
            await queries.mark_schedule_ran(sched["id"], now)
            fired.append(str(sched["id"]))
        except temporal_service.TemporalUnavailable as exc:
            errors.append({"schedule_id": str(sched["id"]), "error": str(exc)})
    return {"checked_at": now.isoformat(), "fired": fired, "errors": errors}
