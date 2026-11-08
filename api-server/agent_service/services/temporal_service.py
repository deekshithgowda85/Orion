"""Thin wrapper around the Temporal client for Layer 1 workflows."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Optional

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from config import get_settings

log = logging.getLogger("temporal")

_connect_lock = asyncio.Lock()


class TemporalUnavailable(Exception):
    pass


async def connect() -> Client:
    s = get_settings()
    return await asyncio.wait_for(
        Client.connect(s.temporal_host, namespace=s.temporal_namespace), timeout=s.temporal_connect_timeout
    )


async def get_client(app: Any) -> Client:
    """Return the cached client, reconnecting lazily if Temporal was down at startup."""
    client: Optional[Client] = getattr(app.state, "temporal", None)
    if client is not None:
        return client
    async with _connect_lock:
        client = getattr(app.state, "temporal", None)
        if client is None:
            try:
                client = await connect()
            except Exception as exc:
                raise TemporalUnavailable(
                    f"Cannot reach Temporal at {get_settings().temporal_host}: {type(exc).__name__}"
                ) from exc
            app.state.temporal = client
    return client


def build_workflow_input(
    *,
    run_id: str,
    tenant_id: str,
    user_id: str,
    ticker: str,
    quarter: Optional[str],
    query: str,
    workflow_type: str,
    priority: str,
) -> dict[str, Any]:
    """THE ONE PLACE that defines what Layer 1's workflow receives. Edit here if your workflow's
    input signature differs.

    `ticker` and `quarter` are top-level AND inside `agent_state`, which is shaped like Layer 3's
    AgentState seed (ticker, quarter, errors). The remaining AgentState keys (market_data,
    filings_data, news_data, quant_data) are produced by the agents, so they are not seeded here.
    `run_id` rides along so progress events can be addressed (add `run_id` to AgentState).
    """
    return {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "ticker": ticker,
        "quarter": quarter,
        "query": query,
        "workflow_type": workflow_type,
        "priority": priority,
        "agent_state": {"ticker": ticker, "quarter": quarter, "errors": [], "run_id": run_id},
    }


async def start_research_workflow(client: Client, **kwargs: Any) -> str:
    s = get_settings()
    payload = build_workflow_input(**kwargs)
    try:
        handle = await client.start_workflow(
            s.temporal_workflow_name,
            payload,
            id=f"research-{kwargs['run_id']}",
            task_queue=s.temporal_task_queue,
            execution_timeout=timedelta(seconds=s.workflow_execution_timeout_seconds),
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            rpc_timeout=timedelta(seconds=15),
        )
    except WorkflowAlreadyStartedError as exc:  # uuid4 collision: practically impossible
        raise TemporalUnavailable("duplicate workflow id") from exc
    return handle.id


async def cancel_workflow(client: Client, run_id: str) -> None:
    await client.get_workflow_handle(f"research-{run_id}").cancel()


async def check_health(client: Client | None) -> bool:
    if client is None:
        return False
    try:
        await asyncio.wait_for(client.service_client.check_health(), timeout=3)
        return True
    except Exception:
        return False
