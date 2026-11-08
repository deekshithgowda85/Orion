"""Shared Temporal client helpers (used by Inngest triggers, worker and CLI)."""
import asyncio
from typing import Any

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import WorkflowAlreadyStartedError

from config import TASK_QUEUE, WORKFLOW_EXECUTION_TIMEOUT, get_settings, workflow_id_for
from models.workflow_models import ResearchRequest
from workflows.research_workflow import ResearchWorkflow

_client: Client | None = None
_lock = asyncio.Lock()


async def connect() -> Client:
    """Open a new Temporal client using the Pydantic v2 data converter."""
    settings = get_settings()
    return await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )


async def get_client() -> Client:
    """Return a lazily created, process-wide Temporal client."""
    global _client
    async with _lock:
        if _client is None:
            _client = await connect()
        return _client


async def start_research(request: ResearchRequest, client: Client | None = None) -> dict[str, Any]:
    """Start a :class:`ResearchWorkflow` idempotently.

    Returns:
        ``{"workflow_id", "run_id", "started"}``; ``started`` is False if a
        workflow with the same ID is already running.
    """
    client = client or await get_client()
    workflow_id = workflow_id_for(request.tenant_id, request.run_id)
    try:
        handle = await client.start_workflow(
            ResearchWorkflow.run,
            request,
            id=workflow_id,
            task_queue=TASK_QUEUE,
            execution_timeout=WORKFLOW_EXECUTION_TIMEOUT,
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
        )
    except WorkflowAlreadyStartedError:
        return {"workflow_id": workflow_id, "run_id": None, "started": False}
    return {"workflow_id": handle.id, "run_id": handle.result_run_id, "started": True}
