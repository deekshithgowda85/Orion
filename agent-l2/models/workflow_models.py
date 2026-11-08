"""Pydantic v2 models for Layer 1 (workflow orchestration).

Every payload that crosses a Temporal boundary (workflow input/output,
activity input/output, signals) is defined here.
"""
import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

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
AgentType = Literal["market_data", "filings", "quant", "news"]
SourceType = Literal["sec_filing", "transcript", "financial_api", "news", "other"]
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

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, populate_by_name=True)


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
    agent_type: AgentType
    priority: int = Field(default=1, ge=1, le=5, description="1 = highest priority")
    depends_on: list[str] = Field(default_factory=list, description="goal_ids that must finish first")
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

    def goal_waves(
        self,
        pending_ids: set[str] | None = None,
        completed_ids: set[str] | None = None,
    ) -> list[list[SubGoal]]:
        """Group sub-goals into waves that can run concurrently.

        Args:
            pending_ids: only schedule these goals (default: all goals).
            completed_ids: goals already finished; they satisfy dependencies.

        Raises:
            ValueError: on a cycle or a dependency that can never be satisfied.
        """
        done: set[str] = set(completed_ids or ())
        remaining = {g.goal_id: g for g in self.goals if pending_ids is None or g.goal_id in pending_ids}
        waves: list[list[SubGoal]] = []
        while remaining:
            ready = [g for g in remaining.values() if set(g.depends_on) <= done]
            if not ready:
                raise ValueError(f"unsatisfiable or cyclic goal dependencies among: {sorted(remaining)}")
            ready.sort(key=lambda g: g.priority)
            waves.append(ready)
            for goal in ready:
                done.add(goal.goal_id)
                del remaining[goal.goal_id]
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
        goal_ids = [g.goal_id for g in self.goals]
        if len(goal_ids) != len(set(goal_ids)):
            raise ValueError("duplicate goal_id values in TaskGraph")
        for goal in self.goals:
            missing_goals = set(goal.depends_on) - set(goal_ids)
            if missing_goals:
                raise ValueError(f"goal {goal.goal_id!r} depends on unknown goals: {sorted(missing_goals)}")
        self.goal_waves()
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
    summary: str = Field(validation_alias=AliasChoices("summary", "executive_summary"))
    sections: list[ReportSection] = Field(default_factory=list)
    citations: list[CitationRef] = Field(default_factory=list)
    confidence_score: float = Field(
        ge=0.0, le=1.0, validation_alias=AliasChoices("confidence_score", "overall_confidence_score")
    )
    conflicts_found: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    trace_log: list[TraceEvent] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------- #
# Layer 2 agent models
# --------------------------------------------------------------------------- #
class VerifiedClaim(_Model):
    """A structured claim extracted from raw tool data, with provenance."""

    claim_id: str
    goal_id: str | None = None
    statement: str | None = Field(default=None, description="One-sentence plain-English claim")
    metric_name: str
    value: float | str | None = None
    unit: str | None = None
    period: str | None = None
    source_type: SourceType = "other"
    source_url: str
    source_title: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    page_ref: str | None = None
    filing_type: str | None = None
    fiscal_period: str | None = None
    extracted_by: str | None = None
    note: str | None = None

    def numeric_value(self) -> float | None:
        """Return ``value`` as a float when it is numeric, else None."""
        if isinstance(self.value, bool) or self.value is None:
            return None
        if isinstance(self.value, (int, float)):
            return float(self.value)
        try:
            return float(str(self.value).replace(",", "").strip())
        except ValueError:
            return None


class ConflictFlag(_Model):
    """Numeric values for the same metric/period that disagree by more than 5%."""

    metric_name: str
    period: str | None = None
    unit: str | None = Field(default=None, description="Unit after normalisation")
    claim_ids: list[str]
    values: dict[str, float] = Field(description="claim_id -> normalised value")
    pct_difference: float = Field(ge=0.0)
    severity: Literal["low", "medium", "high"]
    explanation: str


class NewsEvent(_Model):
    """A key event extracted from news coverage."""

    description: str
    date: str | None = None
    source_url: str | None = None


class NamedEntity(_Model):
    """A named entity mentioned in news coverage."""

    name: str
    entity_type: Literal["company", "person", "regulator", "product", "location", "other"] = "other"


class NewsSummary(_Model):
    """Sentiment, key events and entities for a news sub-goal."""

    goal_id: str | None = None
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    key_events: list[NewsEvent] = Field(default_factory=list)
    entities: list[NamedEntity] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)


class AgentProgress(_Model):
    """Cumulative agent outputs carried between activities and loop iterations."""

    claims: list[VerifiedClaim] = Field(default_factory=list)
    conflict_flags: list[ConflictFlag] = Field(default_factory=list)
    news_summaries: list[NewsSummary] = Field(default_factory=list)
    completed_goal_ids: list[str] = Field(default_factory=list)


class AgentTraceEvent(_Model):
    """Fine-grained agent/LLM trace record (stored in the audit .jsonl)."""

    event_type: Literal["llm_call", "node"] = "llm_call"
    node: str
    run_id: str
    model: str | None = None
    started_at: datetime
    completed_at: datetime
    status: TraceStatus
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    attempts: int = 1
    error: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Activity inputs / outputs
# --------------------------------------------------------------------------- #
class PlannerInput(_Model):
    """Input of PlannerActivity."""

    request: ResearchRequest
    iteration: int = Field(default=1, ge=1)
    prior_task_graph: TaskGraph | None = None
    requery_goals: list[SubGoal] = Field(default_factory=list)


class PlannerOutput(_Model):
    """Output of PlannerActivity."""

    task_graph: TaskGraph
    pending_goal_ids: list[str] = Field(default_factory=list)
    agent_events: list[AgentTraceEvent] = Field(default_factory=list)
    trace: TraceEvent


class ExecutorInput(_Model):
    """Input of ParallelExecutorActivity."""

    request: ResearchRequest
    task_graph: TaskGraph
    goal_ids: list[str] = Field(default_factory=list, description="Goals to run this pass")
    progress: AgentProgress = Field(default_factory=AgentProgress)
    iteration: int = Field(default=1, ge=1)


class ExecutorOutput(_Model):
    """Output of ParallelExecutorActivity (``progress`` is cumulative)."""

    progress: AgentProgress
    results: list[ToolResult] = Field(default_factory=list)  # Layer 3 tool results
    agent_events: list[AgentTraceEvent] = Field(default_factory=list)
    trace: TraceEvent


class VerifierInput(_Model):
    """Input of VerifierActivity."""

    request: ResearchRequest
    task_graph: TaskGraph
    progress: AgentProgress
    results: list[ToolResult] = Field(default_factory=list)
    iteration: int = Field(default=1, ge=1)


class VerifierOutput(_Model):
    """Output of VerifierActivity (``progress`` holds confidence-adjusted claims)."""

    verifications: list[VerificationResult]
    progress: AgentProgress
    citations: list[CitationRef] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    conflicts: list[str] = Field(default_factory=list)
    needs_requery: bool = False
    requery_goals: list[SubGoal] = Field(default_factory=list)
    agent_events: list[AgentTraceEvent] = Field(default_factory=list)
    trace: TraceEvent


class SynthesisInput(_Model):
    """Input of SynthesisActivity."""

    request: ResearchRequest
    task_graph: TaskGraph
    verification: VerifierOutput
    approval: ApprovalDecision
    results: list[ToolResult] = Field(default_factory=list)


class SynthesisOutput(_Model):
    """Output of SynthesisActivity."""

    report: FinalReport
    agent_events: list[AgentTraceEvent] = Field(default_factory=list)
    trace: TraceEvent


class AuditLogInput(_Model):
    """Input of AuditLogActivity."""

    request: ResearchRequest
    report: FinalReport
    approval: ApprovalDecision
    agent_events: list[AgentTraceEvent] = Field(default_factory=list)


class AuditLogOutput(_Model):
    """Output of AuditLogActivity."""

    audit_id: str
    records_written: int = Field(ge=0)
    stored_in: Literal["neon", "local_file"] = "neon"
    trace: TraceEvent
