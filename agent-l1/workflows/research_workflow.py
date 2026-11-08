"""Temporal workflow: ResearchWorkflow.

planner -> parallel executor -> verifier -> [human approval] -> synthesis -> audit log

The 30-minute workflow timeout is applied at start time
(``execution_timeout`` in ``temporal_client.start_research``).
"""
import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from activities.stubs import (
        audit_log_activity,
        parallel_executor_activity,
        planner_activity,
        synthesis_activity,
        verifier_activity,
    )
    from config import APPROVAL_TIMEOUT
    from models.workflow_models import (
        ApprovalDecision,
        AuditLogInput,
        ExecutorInput,
        FinalReport,
        PlannerInput,
        ResearchRequest,
        SynthesisInput,
        VerifierInput,
    )

#: 3 attempts, 10s then 20s backoff. Stubs fail fast: retrying NotImplementedError is pointless.
ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_attempts=3,
    non_retryable_error_types=["NotImplementedError"],
)


@workflow.defn(name="ResearchWorkflow")
class ResearchWorkflow:
    """Durable orchestration of one market-research run."""

    def __init__(self) -> None:
        self._approval: ApprovalDecision | None = None
        self._stage: str = "pending"

    @workflow.signal(name="approve_report")
    def approve_report(self, decision: ApprovalDecision) -> None:
        """Human-in-the-loop signal. The first decision received wins."""
        if self._approval is None:
            self._approval = decision

    @workflow.query(name="current_stage")
    def current_stage(self) -> str:
        """Return the stage the workflow is currently in."""
        return self._stage

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
        timeouts = {
            "planner": timedelta(minutes=5),
            "executor": timedelta(minutes=15),
            "verifier": timedelta(minutes=5),
            "synthesis": timedelta(minutes=5),
            "audit": timedelta(minutes=2),
        }

        # a. Plan
        self._stage = "planning"
        plan = await workflow.execute_activity(
            planner_activity,
            PlannerInput(request=request),
            start_to_close_timeout=timeouts["planner"],
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        # b. Fan-out tool tasks
        self._stage = "executing"
        execution = await workflow.execute_activity(
            parallel_executor_activity,
            ExecutorInput(request=request, task_graph=plan.task_graph),
            start_to_close_timeout=timeouts["executor"],
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        # c. Verify
        self._stage = "verifying"
        verification = await workflow.execute_activity(
            verifier_activity,
            VerifierInput(request=request, task_graph=plan.task_graph, results=execution.results),
            start_to_close_timeout=timeouts["verifier"],
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

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
            synthesis_activity,
            SynthesisInput(
                request=request,
                task_graph=plan.task_graph,
                results=execution.results,
                verification=verification,
                approval=decision,
            ),
            start_to_close_timeout=timeouts["synthesis"],
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        traces = [plan.trace, execution.trace, verification.trace, synthesis.trace]
        report = synthesis.report.model_copy(update={"trace_log": traces})

        # e. Audit log
        self._stage = "auditing"
        audit = await workflow.execute_activity(
            audit_log_activity,
            AuditLogInput(request=request, report=report, approval=decision),
            start_to_close_timeout=timeouts["audit"],
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        self._stage = "completed"
        return report.model_copy(update={"trace_log": [*traces, audit.trace]})
