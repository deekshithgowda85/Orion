"""Pydantic v2 models for Layer 1 (workflow orchestration).

Every payload that crosses a Temporal boundary (workflow input/output,
activity input/output, signals) is defined here.
"""
import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WorkflowType = Literal["deep_audit", "daily_scan", "earnings_pulse"]
ToolName = Literal[
    "market_data",
    "sec_filings",
    "news_search",
    "earnings_transcript",
    "web_search",
    "financial_calc",
]
ToolStatus = Literal["success", "failed", "timeout"]
TraceStatus = Literal["success", "failed"]

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")
_ID_PATTERN = r"^[A-Za-z0-9_\-]+$"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def _new_run_id() -> str:
    """Return a fresh random run identifier."""
    return uuid4().hex


class _Model(BaseModel):
    """Base model: strips whitespace and ignores unknown fields."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# --------------------------------------------------------------------------- #
# Workflow input / signal
# --------------------------------------------------------------------------- #
class ResearchRequest(_Model):
    """Input of :class:`ResearchWorkflow`."""

    ticker: str = Field(description="Stock ticker, e.g. AAPL or BRK.B")
    query: str = Field(min_length=3, max_length=4000)
    workflow_type: WorkflowType
    tenant_id: str = Field(min_length=1, max_length=128, pattern=_ID_PATTERN)
    run_id: str = Field(default_factory=_new_run_id, min_length=1, max_length=128, pattern=_ID_PATTERN)

    @field_validator("ticker")
    @classmethod
    def _normalise_ticker(cls, value: str) -> str:
        """Upper-case the ticker and reject malformed symbols."""
        value = value.strip().upper()
        if not _TICKER_RE.match(value):
            raise ValueError(f"invalid ticker symbol: {value!r}")
        return value


class ApprovalDecision(_Model):
    """Payload of the ``approve_report`` signal."""

    approved: bool = True
    reviewer: str | None = None
    comment: str | None = None


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
class ToolTask(_Model):
    """A single tool invocation inside a sub-goal."""

    task_id: str = Field(min_length=1)
    tool_name: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=120, ge=1, le=900)


class SubGoal(_Model):
    """A decomposed research objective made of one or more tool tasks."""

    goal_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: int = Field(default=1, ge=1, le=5)
    tool_tasks: list[ToolTask] = Field(default_factory=list)


class TaskGraph(_Model):
    """Dependency graph of sub-goals produced by the planner."""

    run_id: str
    goals: list[SubGoal] = Field(min_length=1)

    def all_tasks(self) -> list[ToolTask]:
        """Return every tool task across all goals."""
        return [task for goal in self.goals for task in goal.tool_tasks]

    def execution_waves(self) -> list[list[ToolTask]]:
        """Group tasks into waves; tasks in a wave can run concurrently.

        Raises:
            ValueError: if the dependency graph contains a cycle.
        """
        remaining: dict[str, ToolTask] = {t.task_id: t for t in self.all_tasks()}
        done: set[str] = set()
        waves: list[list[ToolTask]] = []
        while remaining:
            ready = [t for t in remaining.values() if set(t.depends_on) <= done]
            if not ready:
                raise ValueError("TaskGraph contains a dependency cycle")
            waves.append(ready)
            for task in ready:
                done.add(task.task_id)
                del remaining[task.task_id]
        return waves

    @model_validator(mode="after")
    def _validate_graph(self) -> "TaskGraph":
        """Ensure unique task IDs, known dependencies and no cycles."""
        ids = [t.task_id for t in self.all_tasks()]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate task_id values in TaskGraph")
        known = set(ids)
        for task in self.all_tasks():
            missing = set(task.depends_on) - known
            if missing:
                raise ValueError(f"task {task.task_id!r} depends on unknown tasks: {sorted(missing)}")
        self.execution_waves()
        return self


# --------------------------------------------------------------------------- #
# Execution / verification
# --------------------------------------------------------------------------- #
class ToolResult(_Model):
    """Outcome of one :class:`ToolTask`."""

    task_id: str
    tool_name: ToolName
    status: ToolStatus
    output: dict[str, Any] = Field(default_factory=dict)
    source_urls: list[str] = Field(default_factory=list)
    error: str | None = None
    duration_ms: int = Field(default=0, ge=0)


class CitationRef(_Model):
    """A source backing one or more claims."""

    citation_id: str
    source_url: str
    title: str
    publisher: str | None = None
    retrieved_at: datetime = Field(default_factory=_utcnow)
    excerpt: str | None = None
    task_id: str | None = None


class VerificationResult(_Model):
    """Verification outcome for a single claim."""

    claim_id: str
    claim_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_citation_ids: list[str] = Field(default_factory=list)
    contradicting_citation_ids: list[str] = Field(default_factory=list)
    is_conflicted: bool = False
    notes: str | None = None


# --------------------------------------------------------------------------- #
# Tracing / report
# --------------------------------------------------------------------------- #
class TraceEvent(_Model):
    """Audit trace emitted by every activity."""

    activity_name: str
    run_id: str
    started_at: datetime
    completed_at: datetime
    status: TraceStatus
    token_count: int = Field(default=0, ge=0)
    error: str | None = None


class ReportSection(_Model):
    """One titled section of the final report."""

    heading: str
    body: str
    citation_ids: list[str] = Field(default_factory=list)


class FinalReport(_Model):
    """The audited research report returned by the workflow."""

    run_id: str
    ticker: str
    summary: str
    sections: list[ReportSection] = Field(default_factory=list)
    citations: list[CitationRef] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)
    conflicts_found: list[str] = Field(default_factory=list)
    trace_log: list[TraceEvent] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------- #
# Activity inputs / outputs
# --------------------------------------------------------------------------- #
class PlannerInput(_Model):
    """Input of PlannerActivity."""

    request: ResearchRequest


class PlannerOutput(_Model):
    """Output of PlannerActivity."""

    task_graph: TaskGraph
    trace: TraceEvent


class ExecutorInput(_Model):
    """Input of ParallelExecutorActivity."""

    request: ResearchRequest
    task_graph: TaskGraph


class ExecutorOutput(_Model):
    """Output of ParallelExecutorActivity."""

    results: list[ToolResult]
    trace: TraceEvent


class VerifierInput(_Model):
    """Input of VerifierActivity."""

    request: ResearchRequest
    task_graph: TaskGraph
    results: list[ToolResult]


class VerifierOutput(_Model):
    """Output of VerifierActivity."""

    verifications: list[VerificationResult]
    citations: list[CitationRef] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    conflicts: list[str] = Field(default_factory=list)
    trace: TraceEvent


class SynthesisInput(_Model):
    """Input of SynthesisActivity."""

    request: ResearchRequest
    task_graph: TaskGraph
    results: list[ToolResult]
    verification: VerifierOutput
    approval: ApprovalDecision


class SynthesisOutput(_Model):
    """Output of SynthesisActivity."""

    report: FinalReport
    trace: TraceEvent


class AuditLogInput(_Model):
    """Input of AuditLogActivity."""

    request: ResearchRequest
    report: FinalReport
    approval: ApprovalDecision


class AuditLogOutput(_Model):
    """Output of AuditLogActivity."""

    audit_id: str
    records_written: int = Field(ge=0)
    trace: TraceEvent
