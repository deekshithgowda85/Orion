"""Layer 2 implementations of the five Temporal activities.

Each activity builds an ``AgentState`` from its typed Pydantic input, runs the
corresponding LangGraph node (the same node functions ``agents/graph.py``
wires together) and returns a typed Pydantic output. The self-correction loop
of the graph (verifier -> planner) is mirrored durably by ``ResearchWorkflow``.
"""
import json
import uuid
from typing import Any

from temporalio import activity

from activities.audit_store import store_trace
from activities.stubs import traced  # trace helper from Layer 1
from agents.parallel_executor import parallel_executor_node
from agents.planner import planner_node
from agents.state import initial_state
from agents.synthesizer import synthesizer_node
from agents.verifier import verifier_node
from models.workflow_models import (
    AgentProgress,
    AgentTraceEvent,
    AuditLogInput,
    AuditLogOutput,
    ExecutorInput,
    ExecutorOutput,
    PlannerInput,
    PlannerOutput,
    SynthesisInput,
    SynthesisOutput,
    VerifierInput,
    VerifierOutput,
)


def _tokens(events: list[dict[str, Any]]) -> int:
    """Total LLM tokens across trace events."""
    return sum(int(e.get("total_tokens", 0)) for e in events)


def _progress_from_state(state: dict[str, Any]) -> AgentProgress:
    return AgentProgress(
        claims=state.get("verified_claims", []),
        conflict_flags=state.get("conflicts", []),
        news_summaries=state.get("news_summaries", []),
        completed_goal_ids=state.get("completed_goal_ids", []),
    )


def _load_progress(state: dict[str, Any], progress: AgentProgress) -> None:
    state["verified_claims"] = list(progress.claims)
    state["conflicts"] = list(progress.conflict_flags)
    state["news_summaries"] = list(progress.news_summaries)
    state["completed_goal_ids"] = list(progress.completed_goal_ids)


@activity.defn(name="PlannerActivity")
async def planner_activity(payload: PlannerInput) -> PlannerOutput:
    """Create (or extend, on re-query passes) the TaskGraph."""
    async with traced("PlannerActivity", payload.request.run_id) as rec:
        state = initial_state(payload.request, iteration=payload.iteration - 1)
        state["task_graph"] = payload.prior_task_graph
        state["requery_goals"] = list(payload.requery_goals)
        out = await planner_node(state)
        events = out["trace_events"]
        rec.token_count = _tokens(events)
        return PlannerOutput(
            task_graph=out["task_graph"],  # type: ignore[arg-type]
            pending_goal_ids=out["pending_goal_ids"],
            agent_events=[AgentTraceEvent.model_validate(e) for e in events],
            trace=rec.success(),
        )


@activity.defn(name="ParallelExecutorActivity")
async def parallel_executor_activity(payload: ExecutorInput) -> ExecutorOutput:
    """Run the pending sub-goals through the specialist executors."""
    async with traced("ParallelExecutorActivity", payload.request.run_id) as rec:
        state = initial_state(payload.request, iteration=payload.iteration)
        state["task_graph"] = payload.task_graph
        state["pending_goal_ids"] = list(payload.goal_ids)
        _load_progress(state, payload.progress)
        activity.heartbeat({"goals": payload.goal_ids})
        out = await parallel_executor_node(state)
        events = out["trace_events"]
        rec.token_count = _tokens(events)
        return ExecutorOutput(
            progress=_progress_from_state(out),
            agent_events=[AgentTraceEvent.model_validate(e) for e in events],
            trace=rec.success(),
        )


@activity.defn(name="VerifierActivity")
async def verifier_activity(payload: VerifierInput) -> VerifierOutput:
    """Verify claims, apply source authority and propose re-query goals."""
    async with traced("VerifierActivity", payload.request.run_id) as rec:
        state = initial_state(payload.request, iteration=payload.iteration)
        state["task_graph"] = payload.task_graph
        _load_progress(state, payload.progress)
        out = await verifier_node(state)
        events = out["trace_events"]
        rec.token_count = _tokens(events)
        return VerifierOutput(
            verifications=out["verifications"],
            progress=_progress_from_state(out),
            citations=out["citations"],
            overall_confidence=out["overall_confidence"],
            conflicts=out["conflict_notes"],
            needs_requery=out["needs_requery"],
            requery_goals=out["requery_goals"],
            agent_events=[AgentTraceEvent.model_validate(e) for e in events],
            trace=rec.success(),
        )


@activity.defn(name="SynthesisActivity")
async def synthesis_activity(payload: SynthesisInput) -> SynthesisOutput:
    """Assemble the cited FinalReport."""
    async with traced("SynthesisActivity", payload.request.run_id) as rec:
        verification = payload.verification
        state = initial_state(payload.request)
        state["task_graph"] = payload.task_graph
        _load_progress(state, verification.progress)
        state["citations"] = list(verification.citations)
        state["conflict_notes"] = list(verification.conflicts)
        state["overall_confidence"] = verification.overall_confidence
        state["reviewer_note"] = (
            f"Reviewer note ({payload.approval.reviewer or 'unknown'}): {payload.approval.comment}"
            if payload.approval.comment else "")
        out = await synthesizer_node(state)
        events = out["trace_events"]
        rec.token_count = _tokens(events)
        return SynthesisOutput(
            report=out["final_report"],  # type: ignore[arg-type]
            agent_events=[AgentTraceEvent.model_validate(e) for e in events],
            trace=rec.success(),
        )


@activity.defn(name="AuditLogActivity")
async def audit_log_activity(payload: AuditLogInput) -> AuditLogOutput:
    """Serialise all trace events to ``.jsonl`` and write them to Neon (``workflow_traces``)."""
    async with traced("AuditLogActivity", payload.request.run_id) as rec:
        report = payload.report
        records: list[dict[str, Any]] = [
            {"type": "run", "run_id": report.run_id, "tenant_id": payload.request.tenant_id,
             "ticker": report.ticker, "workflow_type": payload.request.workflow_type,
             "approved_by": payload.approval.reviewer, "approved": payload.approval.approved}]
        records += [{"type": "activity_trace", **e.model_dump(mode="json")} for e in report.trace_log]
        records += [{"type": "agent_trace", **e.model_dump(mode="json")} for e in payload.agent_events]
        records.append({"type": "report_summary", "confidence_score": report.confidence_score,
                        "conflicts": len(report.conflicts_found), "risk_flags": len(report.risk_flags),
                        "citations": len(report.citations), "sources": report.data_sources})
        jsonl = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
        audit_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{payload.request.tenant_id}/{payload.request.run_id}"))
        stored_in = await store_trace(
            audit_id=audit_id, tenant_id=payload.request.tenant_id, run_id=payload.request.run_id,
            ticker=report.ticker, workflow_type=payload.request.workflow_type, record_count=len(records),
            confidence=report.confidence_score, jsonl=jsonl)
        return AuditLogOutput(audit_id=audit_id, records_written=len(records), stored_in=stored_in,  # type: ignore[arg-type]
                              trace=rec.success())


ALL_ACTIVITIES = [planner_activity, parallel_executor_activity, verifier_activity,
                  synthesis_activity, audit_log_activity]
