"""Pydantic v2 models for research endpoints."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkflowType(str, Enum):
    full_research = "full_research"
    earnings_analysis = "earnings_analysis"
    competitor_comparison = "competitor_comparison"
    sec_filing_digest = "sec_filing_digest"
    technical_snapshot = "technical_snapshot"


class Priority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"


class RunState(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ResearchSubmitRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ticker: str = Field(..., min_length=1, max_length=10, pattern=r"^[A-Za-z0-9.\-]{1,10}$")
    quarter: Optional[str] = Field(
        None, max_length=16, pattern=r"^[A-Za-z0-9 _\-]{1,16}$",
        description="Fiscal quarter passed to Layer 3 as AgentState.quarter, e.g. '2025Q3'. Format is not interpreted here.",
    )
    query: str = Field(..., min_length=3, max_length=2000)
    workflow_type: WorkflowType = WorkflowType.full_research
    priority: Priority = Priority.normal

    @field_validator("ticker")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("quarter")
    @classmethod
    def strip_quarter(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() or None if v else None


class ResearchSubmitResponse(BaseModel):
    run_id: UUID
    status: Literal["queued"] = "queued"
    estimated_duration_seconds: int


class RunStatus(BaseModel):
    run_id: UUID
    ticker: Optional[str] = None
    quarter: Optional[str] = None
    status: RunState
    current_step: Optional[str] = None
    progress_pct: int = Field(0, ge=0, le=100)
    started_at: datetime
    duration_so_far: float = Field(..., description="Seconds since the run started (or total if finished)")


class Citation(BaseModel):
    id: UUID
    run_id: UUID
    source_url: Optional[str] = None
    source_type: Optional[str] = None
    metric_name: Optional[str] = None
    value: Optional[str] = None
    period: Optional[str] = None
    confidence: Optional[float] = None
    raw_snippet: Optional[str] = None


class FinalReport(BaseModel):
    run_id: UUID
    ticker: str
    quarter: Optional[str] = None
    query: str
    workflow_type: str
    generated_at: Optional[datetime] = None
    summary: str = ""
    sections: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] = Field(
        default_factory=dict,
        description="The complete report_jsonb exactly as stored by Layers 1-3 (nothing is dropped).",
    )


class RunSummary(BaseModel):
    run_id: UUID
    ticker: str
    quarter: Optional[str] = None
    query: str
    workflow_type: str
    status: RunState
    current_step: Optional[str] = None
    progress_pct: int
    started_at: datetime
    completed_at: Optional[datetime] = None


class RunHistoryPage(BaseModel):
    items: list[RunSummary]
    page: int
    page_size: int
    total: int
    total_pages: int


class StreamEvent(BaseModel):
    type: Literal["step_started", "step_completed", "conflict_found", "report_ready"]
    payload: dict[str, Any] = Field(default_factory=dict)
