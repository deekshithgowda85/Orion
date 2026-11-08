"""Workflow template and schedule routes."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from db import queries
from middleware.auth import AuthUser
from models.research import WorkflowType
from models.workflows import ScheduleCreateRequest, ScheduleList, ScheduleResponse, WorkflowTemplate
from services import inngest_service

log = logging.getLogger("workflows")
router = APIRouter(prefix="/workflows", tags=["workflows"])

TEMPLATES = [
    WorkflowTemplate(
        id="full-research", name="Full Research Report", workflow_type=WorkflowType.full_research,
        description="Market data, SEC filings, web research and conflict resolution into a cited report.",
        estimated_duration_seconds=900, default_query="Provide a comprehensive investment research report.",
    ),
    WorkflowTemplate(
        id="earnings", name="Earnings Analysis", workflow_type=WorkflowType.earnings_analysis,
        description="Latest earnings results vs. consensus, guidance changes and key drivers.",
        estimated_duration_seconds=420, default_query="Analyze the most recent earnings release.",
    ),
    WorkflowTemplate(
        id="competitors", name="Competitor Comparison", workflow_type=WorkflowType.competitor_comparison,
        description="Side-by-side comparison against the closest public peers.",
        estimated_duration_seconds=720, default_query="Compare against its top competitors.",
    ),
    WorkflowTemplate(
        id="sec-digest", name="SEC Filing Digest", workflow_type=WorkflowType.sec_filing_digest,
        description="Summarize recent 10-K, 10-Q and 8-K filings and flag material changes.",
        estimated_duration_seconds=360, default_query="Summarize recent SEC filings and material changes.",
    ),
    WorkflowTemplate(
        id="technical", name="Technical Snapshot", workflow_type=WorkflowType.technical_snapshot,
        description="Price action, trend and volume indicators from market data.",
        estimated_duration_seconds=180, default_query="Give a technical snapshot of recent price action.",
    ),
]


def _user(request: Request) -> AuthUser:
    return request.state.user


def _to_response(row: dict) -> ScheduleResponse:
    return ScheduleResponse(
        id=row["id"], tenant_id=row["tenant_id"], inngest_schedule_id=row["inngest_schedule_id"],
        ticker=row["ticker"], workflow_type=row["workflow_type"], cron_expr=row["cron_expr"],
        active=row["active"], created_at=row["created_at"], last_run_at=row.get("last_run_at"),
    )


@router.get("/templates", response_model=list[WorkflowTemplate])
async def list_templates() -> list[WorkflowTemplate]:
    return TEMPLATES


@router.get("/schedules", response_model=ScheduleList)
async def list_schedules(request: Request) -> ScheduleList:
    rows = await queries.list_schedules(_user(request).tenant_id)
    return ScheduleList(items=[_to_response(r) for r in rows])


@router.post("/schedule", response_model=ScheduleResponse, status_code=201)
async def create_schedule(body: ScheduleCreateRequest, request: Request) -> ScheduleResponse:
    user = _user(request)
    if user.role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Only org admins can create schedules")
    template = next(t for t in TEMPLATES if t.workflow_type == body.workflow_type)
    query = body.query or template.default_query
    row = await queries.create_schedule(
        user.tenant_id, None, body.ticker, body.workflow_type.value, body.cron_expr, query
    )
    warning = None
    if inngest_service.enabled():
        try:
            await inngest_service.send_event(
                "research/schedule.created",
                {"schedule_id": str(row["id"]), "tenant_id": str(user.tenant_id), "ticker": body.ticker,
                 "workflow_type": body.workflow_type.value, "cron_expr": body.cron_expr},
            )
        except inngest_service.InngestError as exc:
            warning = f"Schedule stored, but Inngest was not notified: {exc}"
    else:
        warning = "Schedule stored. INNGEST_EVENT_KEY is not set, so Inngest was not notified; runs still fire if something calls POST /internal/schedules/run-due every minute."
    resp = _to_response(row)
    resp.warning = warning
    return resp


@router.delete("/schedule/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: UUID, request: Request) -> Response:
    user = _user(request)
    if user.role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Only org admins can delete schedules")
    row = await queries.get_schedule(schedule_id, user.tenant_id)
    if row is None or not row["active"]:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await queries.deactivate_schedule(schedule_id, user.tenant_id)
    if inngest_service.enabled():
        try:
            await inngest_service.send_event(
                "research/schedule.deleted", {"schedule_id": str(schedule_id), "tenant_id": str(user.tenant_id)}
            )
        except inngest_service.InngestError:
            log.warning("inngest delete notification failed", extra={"schedule_id": str(schedule_id)})
    return Response(status_code=204)
