"""Layer 1 activity stubs.

Every activity has typed Pydantic input/output and emits a trace event
``{activity_name, run_id, started_at, completed_at, status, token_count, error}``
(logged as JSON; on success it is also returned inside the output model).

Layer 2 replaces each ``raise NotImplementedError`` with real logic and
finishes with ``return <Output>(..., trace=rec.success())``.
"""
import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from temporalio import activity

from models.workflow_models import (
    AuditLogInput,
    AuditLogOutput,
    ExecutorInput,
    ExecutorOutput,
    PlannerInput,
    PlannerOutput,
    ResearchRequest,
    SynthesisInput,
    SynthesisOutput,
    ToolResult,
    ToolTask,
    TraceEvent,
    VerifierInput,
    VerifierOutput,
)


# --------------------------------------------------------------------------- #
# Trace helpers
# --------------------------------------------------------------------------- #
class TraceRecorder:
    """Collects timing/token data for one activity execution."""

    def __init__(self, activity_name: str, run_id: str) -> None:
        self.activity_name = activity_name
        self.run_id = run_id
        self.started_at = datetime.now(timezone.utc)
        self.token_count = 0
        self._event: TraceEvent | None = None

    def build(self, status: str, error: str | None = None) -> TraceEvent:
        """Build and cache the final :class:`TraceEvent`."""
        self._event = TraceEvent(
            activity_name=self.activity_name,
            run_id=self.run_id,
            started_at=self.started_at,
            completed_at=datetime.now(timezone.utc),
            status=status,  # type: ignore[arg-type]
            token_count=self.token_count,
            error=error,
        )
        return self._event

    def success(self) -> TraceEvent:
        """Return the cached success event, building it on first call."""
        return self._event or self.build("success")


def _emit(event: TraceEvent) -> None:
    """Log the trace event as a single JSON line."""
    activity.logger.info("trace_event %s", json.dumps(event.model_dump(mode="json")))


@asynccontextmanager
async def traced(activity_name: str, run_id: str) -> AsyncIterator[TraceRecorder]:
    """Emit a trace event when the wrapped activity body finishes or fails."""
    rec = TraceRecorder(activity_name, run_id)
    try:
        yield rec
    except (Exception, asyncio.CancelledError) as exc:
        _emit(rec.build("failed", f"{type(exc).__name__}: {exc}"))
        raise
    else:
        _emit(rec.success())


# --------------------------------------------------------------------------- #
# a. PlannerActivity
# --------------------------------------------------------------------------- #
@activity.defn(name="PlannerActivity")
async def planner_activity(payload: PlannerInput) -> PlannerOutput:
    """Decompose the research query into a :class:`TaskGraph`."""
    async with traced("PlannerActivity", payload.request.run_id):
        # Implemented in Layer 2
        raise NotImplementedError("PlannerActivity is implemented in Layer 2")


# --------------------------------------------------------------------------- #
# b. ParallelExecutorActivity
# --------------------------------------------------------------------------- #
async def _dispatch_tool(task: ToolTask, request: ResearchRequest) -> dict[str, Any]:
    """Call the real tool for ``task`` and return its raw output dict."""
    # Implemented in Layer 2
    raise NotImplementedError(f"Tool '{task.tool_name}' is implemented in Layer 2")


async def _run_tool_task(task: ToolTask, request: ResearchRequest) -> ToolResult:
    """Run one tool task with its own timeout and convert it to a :class:`ToolResult`."""
    started = time.monotonic()
    try:
        output = await asyncio.wait_for(_dispatch_tool(task, request), timeout=task.timeout_seconds)
    except asyncio.TimeoutError:
        return ToolResult(
            task_id=task.task_id,
            tool_name=task.tool_name,
            status="timeout",
            error=f"timed out after {task.timeout_seconds}s",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    return ToolResult(
        task_id=task.task_id,
        tool_name=task.tool_name,
        status="success",
        output=output,
        source_urls=list(output.get("source_urls", [])),
        duration_ms=int((time.monotonic() - started) * 1000),
    )


@activity.defn(name="ParallelExecutorActivity")
async def parallel_executor_activity(payload: ExecutorInput) -> ExecutorOutput:
    """Fan out tool tasks wave by wave with ``asyncio.gather``.

    Tasks with no unmet dependencies run concurrently; a task whose upstream
    dependency failed is skipped and reported as failed.
    """
    async with traced("ParallelExecutorActivity", payload.request.run_id) as rec:
        results: list[ToolResult] = []
        failed_ids: set[str] = set()

        for wave_no, wave in enumerate(payload.task_graph.execution_waves(), start=1):
            runnable: list[ToolTask] = []
            for task in wave:
                if failed_ids & set(task.depends_on):
                    results.append(
                        ToolResult(
                            task_id=task.task_id,
                            tool_name=task.tool_name,
                            status="failed",
                            error="skipped: upstream dependency failed",
                        )
                    )
                    failed_ids.add(task.task_id)
                else:
                    runnable.append(task)

            activity.heartbeat({"wave": wave_no, "tasks": len(runnable)})
            wave_results = await asyncio.gather(*(_run_tool_task(t, payload.request) for t in runnable))
            for result in wave_results:
                results.append(result)
                if result.status != "success":
                    failed_ids.add(result.task_id)

        return ExecutorOutput(results=results, trace=rec.success())


# --------------------------------------------------------------------------- #
# c. VerifierActivity
# --------------------------------------------------------------------------- #
@activity.defn(name="VerifierActivity")
async def verifier_activity(payload: VerifierInput) -> VerifierOutput:
    """Check results for contradictions and score confidence per claim."""
    async with traced("VerifierActivity", payload.request.run_id):
        # Implemented in Layer 2
        raise NotImplementedError("VerifierActivity is implemented in Layer 2")


# --------------------------------------------------------------------------- #
# d. SynthesisActivity
# --------------------------------------------------------------------------- #
@activity.defn(name="SynthesisActivity")
async def synthesis_activity(payload: SynthesisInput) -> SynthesisOutput:
    """Assemble the final cited report from verified results."""
    async with traced("SynthesisActivity", payload.request.run_id):
        # Implemented in Layer 2
        raise NotImplementedError("SynthesisActivity is implemented in Layer 2")


# --------------------------------------------------------------------------- #
# e. AuditLogActivity
# --------------------------------------------------------------------------- #
@activity.defn(name="AuditLogActivity")
async def audit_log_activity(payload: AuditLogInput) -> AuditLogOutput:
    """Write the run's ``.jsonl`` trace to Neon."""
    async with traced("AuditLogActivity", payload.request.run_id):
        # Implemented in Layer 2
        raise NotImplementedError("AuditLogActivity is implemented in Layer 2")


ALL_ACTIVITIES = [
    planner_activity,
    parallel_executor_activity,
    verifier_activity,
    synthesis_activity,
    audit_log_activity,
]
