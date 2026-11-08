"""Pydantic v2 models for workflow template / schedule endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from models.research import WorkflowType


class WorkflowTemplate(BaseModel):
    id: str
    name: str
    workflow_type: WorkflowType
    description: str
    estimated_duration_seconds: int
    default_query: str


class ScheduleCreateRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10, pattern=r"^[A-Za-z0-9.\-]{1,10}$")
    workflow_type: WorkflowType
    cron_expr: str = Field(..., description="5-field cron expression, e.g. '0 9 * * 1-5' (UTC)")
    quarter: Optional[str] = Field(None, max_length=16, pattern=r"^[A-Za-z0-9 _\-]{1,16}$")
    query: Optional[str] = Field(None, max_length=2000)

    @field_validator("ticker")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("cron_expr")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        from croniter import croniter

        parts = v.split()
        if len(parts) != 5:
            raise ValueError("cron_expr must have exactly 5 fields")
        if not croniter.is_valid(" ".join(parts)):
            raise ValueError("cron_expr is not a valid cron expression")
        return " ".join(parts)


class ScheduleResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    inngest_schedule_id: Optional[str] = None
    ticker: str
    workflow_type: str
    cron_expr: str
    active: bool
    created_at: datetime
    last_run_at: Optional[datetime] = None
    warning: Optional[str] = Field(None, description="Set when the schedule was stored but Inngest was not notified")


class ScheduleList(BaseModel):
    items: list[ScheduleResponse]
