"""Research routes: submit, status, SSE stream, report, history."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from config import get_settings
from db import queries
from integration.progress_events import channel_for
from logging_config import run_id_ctx
from middleware.auth import AuthUser
from models.research import (
    Citation,
    FinalReport,
    ResearchSubmitRequest,
    ResearchSubmitResponse,
    RunHistoryPage,
    RunState,
    RunStatus,
    RunSummary,
    WorkflowType,
)
from services import report_service, run_submit, temporal_service

log = logging.getLogger("research")
router = APIRouter(prefix="/research", tags=["research"])

ESTIMATED_SECONDS = {
    WorkflowType.full_research: 900,
    WorkflowType.earnings_analysis: 420,
    WorkflowType.competitor_comparison: 720,
    WorkflowType.sec_filing_digest: 360,
    WorkflowType.technical_snapshot: 180,
}
PRIORITY_MULTIPLIER = {"high": 0.8, "normal": 1.0, "low": 1.3}
TERMINAL = ("completed", "failed", "cancelled")


def _user(request: Request) -> AuthUser:
    return request.state.user


def _duration(row: dict) -> float:
    end = row["completed_at"] or datetime.now(timezone.utc)
    return round((end - row["started_at"]).total_seconds(), 2)


# ------------------------------------------------------------------ submit
@router.post("/submit", response_model=ResearchSubmitResponse, status_code=202)
async def submit_research(body: ResearchSubmitRequest, request: Request) -> ResearchSubmitResponse:
    user = _user(request)
    quarter = body.quarter or (get_settings().default_quarter or None)
    try:
        run_id = await run_submit.submit_run(
            request.app,
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            ticker=body.ticker,
            quarter=quarter,
            query=body.query,
            workflow_type=body.workflow_type.value,
            priority=body.priority.value,
        )
    except temporal_service.TemporalUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Workflow engine unavailable: {exc}") from exc
    run_id_ctx.set(str(run_id))
    est = int(ESTIMATED_SECONDS[body.workflow_type] * PRIORITY_MULTIPLIER[body.priority.value])
    return ResearchSubmitResponse(run_id=run_id, estimated_duration_seconds=est)


# ----------------------------------------------------------------- history
@router.get("/history", response_model=RunHistoryPage)
async def run_history(
    request: Request,
    ticker: Optional[str] = Query(None, max_length=10),
    workflow_type: Optional[WorkflowType] = None,
    status: Optional[RunState] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
) -> RunHistoryPage:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    user = _user(request)
    rows, total = await queries.list_runs_by_tenant(
        user.tenant_id,
        ticker=ticker,
        workflow_type=workflow_type.value if workflow_type else None,
        status=status.value if status else None,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    items = [
        RunSummary(
            run_id=r["id"], ticker=r["ticker"], quarter=r.get("quarter"), query=r["query"],
            workflow_type=r["workflow_type"], status=r["status"], current_step=r["current_step"],
            progress_pct=r["progress_pct"], started_at=r["started_at"], completed_at=r["completed_at"],
        )
        for r in rows
    ]
    return RunHistoryPage(
        items=items, page=page, page_size=page_size, total=total, total_pages=max(1, math.ceil(total / page_size))
    )


# ------------------------------------------------------------------ status
async def _require_run(run_id: UUID, user: AuthUser) -> dict:
    run_id_ctx.set(str(run_id))
    row = await queries.get_run(run_id, user.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


@router.get("/{run_id}/status", response_model=RunStatus)
async def run_status(run_id: UUID, request: Request) -> RunStatus:
    row = await _require_run(run_id, _user(request))
    return RunStatus(
        run_id=row["id"], ticker=row["ticker"], quarter=row.get("quarter"), status=row["status"],
        current_step=row["current_step"], progress_pct=row["progress_pct"], started_at=row["started_at"],
        duration_so_far=_duration(row),
    )


# ------------------------------------------------------------------ stream
def _sse(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/{run_id}/stream")
async def stream_run(run_id: UUID, request: Request) -> StreamingResponse:
    user = _user(request)
    row = await _require_run(run_id, user)
    settings = get_settings()
    redis = request.app.state.redis

    async def gen() -> AsyncIterator[str]:
        pubsub = redis.pubsub()
        try:
            # Subscribe BEFORE checking the DB so a report_ready published in between is not missed.
            await pubsub.subscribe(channel_for(str(run_id)))
        except Exception:
            yield _sse("error", {"detail": "event bus (Redis) unavailable"})
            return
        deadline = time.monotonic() + settings.sse_timeout_seconds
        last_beat = last_poll = time.monotonic()
        try:
            yield _sse("connected", {"run_id": str(run_id), "status": row["status"]})
            status = row["status"]
            first = True
            while True:
                # Terminal-state check: covers runs that finished before we connected, and runs that
                # failed/crashed (no report_ready is ever published for those).
                if first or time.monotonic() - last_poll >= settings.sse_status_poll_seconds:
                    first = False
                    last_poll = time.monotonic()
                    try:
                        status = await queries.get_run_status_by_id(run_id, user.tenant_id) or status
                    except Exception:
                        log.warning("status poll failed inside SSE loop")
                    if status in TERMINAL:
                        if status == "completed":
                            yield _sse("report_ready", {"type": "report_ready", "payload": {"run_id": str(run_id)}})
                        else:
                            yield _sse("run_ended", {"type": "run_ended", "payload": {"status": status}})
                        return
                if await request.is_disconnected():
                    return
                if time.monotonic() >= deadline:
                    yield _sse("timeout", {"detail": "stream closed after the 35 minute limit"})
                    return
                try:
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                except Exception:
                    yield _sse("error", {"detail": "event bus (Redis) connection lost"})
                    return
                if msg and msg.get("type") == "message":
                    try:
                        evt = json.loads(msg["data"])
                    except json.JSONDecodeError:
                        continue
                    etype = evt.get("type", "message")
                    yield _sse(etype, evt)
                    if etype == "report_ready":
                        return
                elif time.monotonic() - last_beat > 15:
                    last_beat = time.monotonic()
                    yield ": keep-alive\n\n"
                else:
                    await asyncio.sleep(0)
        finally:
            try:
                await pubsub.unsubscribe(channel_for(str(run_id)))
                await pubsub.aclose()
            except Exception:
                pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------ report
def _dict_list(v: object) -> list[dict]:
    if not isinstance(v, list):
        return []
    return [x if isinstance(x, dict) else {"description": str(x)} for x in v]


@router.get("/{run_id}/report", response_model=FinalReport)
async def get_report(run_id: UUID, request: Request, format: str = Query("json", pattern="^(json|pdf)$")):
    user = _user(request)
    row = await _require_run(run_id, user)
    if row["status"] != "completed" or not row["report_jsonb"]:
        raise HTTPException(status_code=409, detail=f"Report not ready (status={row['status']})")
    citations = await queries.list_citations_by_run(run_id)
    stored = row["report_jsonb"]
    base = dict(stored) if isinstance(stored, dict) else {"value": stored}
    meta = base.get("metadata")
    report = FinalReport(
        run_id=row["id"],
        ticker=row["ticker"],
        quarter=row.get("quarter"),
        query=row["query"],
        workflow_type=row["workflow_type"],
        generated_at=row["completed_at"],
        summary=str(base.get("summary") or base.get("executive_summary") or ""),
        sections=_dict_list(base.get("sections")),
        conflicts=_dict_list(base.get("conflicts")),
        citations=[Citation(**c) for c in citations],
        metadata=meta if isinstance(meta, dict) else {},
        report=base,
    )
    if format == "pdf":
        md = report_service.report_to_markdown(report.model_dump(mode="json"))
        try:
            pdf = await report_service.markdown_to_pdf(md)
        except report_service.PdfUnavailable as exc:
            raise HTTPException(status_code=501, detail=f"PDF export unavailable: {exc}") from exc
        except Exception as exc:
            log.exception("pdf conversion failed")
            raise HTTPException(status_code=500, detail="PDF generation failed") from exc
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{row["ticker"]}-{run_id}.pdf"'},
        )
    return report
