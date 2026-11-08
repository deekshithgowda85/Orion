"""Temporal workflow: ResearchWorkflow (Layer 2 version).

    +--> planner -> parallel executor -> verifier --+
    |                                               | needs_requery and iteration < MAX_ITERATIONS
    +-----------------------------------------------+
                           |
                    [human approval] -> synthesis -> audit log

The loop is the durable twin of the conditional edge in ``agents/graph.py``.
Activities are referenced by name so the workflow sandbox never imports
LangGraph or the Groq SDK. The 30-minute timeout is applied at start time
(``execution_timeout`` in ``temporal_client.start_research``).
"""
import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from agents.state import MAX_ITERATIONS
    from config import APPROVAL_TIMEOUT
    from models.workflow_models import (
        AgentProgress,
        AgentTraceEvent,
        ApprovalDecision,
        AuditLogInput,
        AuditLogOutput,
        ExecutorInput,
        ExecutorOutput,
        FinalReport,
        PlannerInput,
        PlannerOutput,
        ResearchRequest,
        SubGoal,
        SynthesisInput,
        SynthesisOutput,
        TaskGraph,
        TraceEvent,
        VerifierInput,
        VerifierOutput,
    )

#: 3 attempts, 10s then 20s backoff. Bad credentials are never retried.
ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_attempts=3,
    non_retryable_error_types=["LLMConfigError"],
)


@workflow.defn(name="ResearchWorkflow")
class ResearchWorkflow:
    """Durable orchestration of one market-research run."""

    def __init__(self) -> None:
        self._approval: ApprovalDecision | None = None
        self._stage: str = "pending"
        self._iteration: int = 0

    @workflow.signal(name="approve_report")
    def approve_report(self, decision: ApprovalDecision) -> None:
        """Human-in-the-loop signal. The first decision received wins."""
        if self._approval is None:
            self._approval = decision

    @workflow.query(name="current_stage")
    def current_stage(self) -> str:
        """Return the stage (and loop iteration) the workflow is in."""
        return f"{self._stage} (iteration {self._iteration})" if self._iteration else self._stage

    async def _await_approval(self) -> ApprovalDecision:
        """Block until a reviewer signals, or auto-approve after 5 minutes."""
        try:
            await workflow.wait_condition(lambda: self._approval is not None, timeout=APPROVAL_TIMEOUT)
        except asyncio.TimeoutError:
            self._approval = ApprovalDecision(
                approved=True,
                reviewer="system:auto-approve",
                comment=f"No reviewer signal within {int(APPROVAL_TIMEOUT.total_seconds() // 60)} minutes",
            )
            workflow.logger.info("approve_report timed out; auto-approved")
        assert self._approval is not None
        return self._approval

    @workflow.run
    async def run(self, request: ResearchRequest) -> FinalReport:
        """Execute the research pipeline and return the audited report."""
        task_graph: TaskGraph | None = None
        progress = AgentProgress()
        requery_goals: list[SubGoal] = []
        traces: list[TraceEvent] = []
        agent_events: list[AgentTraceEvent] = []
        verification: VerifierOutput | None = None

        for iteration in range(1, MAX_ITERATIONS + 1):
            self._iteration = iteration

            # a. Plan (initial plan, or refine verifier re-query goals)
            self._stage = "planning"
            plan = await workflow.execute_activity(
                "PlannerActivity",
                PlannerInput(request=request, iteration=iteration, prior_task_graph=task_graph,
                             requery_goals=requery_goals),
                result_type=PlannerOutput,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )
            task_graph = plan.task_graph
            traces.append(plan.trace)
            agent_events += plan.agent_events

            # b. Fan out the pending goals
            self._stage = "executing"
            execution = await workflow.execute_activity(
                "ParallelExecutorActivity",
                ExecutorInput(request=request, task_graph=task_graph, goal_ids=plan.pending_goal_ids,
                              progress=progress, iteration=iteration),
                result_type=ExecutorOutput,
                start_to_close_timeout=timedelta(minutes=15),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )
            progress = execution.progress
            traces.append(execution.trace)
            agent_events += execution.agent_events

            # c. Verify
            self._stage = "verifying"
            verification = await workflow.execute_activity(
                "VerifierActivity",
                VerifierInput(request=request, task_graph=task_graph, progress=progress,
                              results=execution.results, iteration=iteration),
                result_type=VerifierOutput,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )
            progress = verification.progress  # confidence-adjusted claims
            traces.append(verification.trace)
            agent_events += verification.agent_events

            if not verification.needs_requery or iteration == MAX_ITERATIONS:
                break
            requery_goals = verification.requery_goals
            workflow.logger.info("self-correction: iteration %s -> %s re-query goals", iteration, len(requery_goals))

        assert verification is not None and task_graph is not None

        # Human-in-the-loop gate (pauses synthesis)
        self._stage = "awaiting_approval"
        decision = await self._await_approval()
        if not decision.approved:
            raise ApplicationError(
                f"Report rejected by {decision.reviewer or 'reviewer'}: {decision.comment or 'no comment'}",
                non_retryable=True,
            )

        # d. Synthesise
        self._stage = "synthesizing"
        synthesis = await workflow.execute_activity(
            "SynthesisActivity",
            SynthesisInput(request=request, task_graph=task_graph, verification=verification, approval=decision),
            result_type=SynthesisOutput,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        traces.append(synthesis.trace)
        agent_events += synthesis.agent_events
        report = synthesis.report.model_copy(update={"trace_log": traces})

        # e. Audit log
        self._stage = "auditing"
        audit = await workflow.execute_activity(
            "AuditLogActivity",
            AuditLogInput(request=request, report=report, approval=decision, agent_events=agent_events),
            result_type=AuditLogOutput,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        self._stage = "completed"
        return report.model_copy(update={"trace_log": [*traces, audit.trace]})
