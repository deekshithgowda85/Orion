"""Standalone Redis progress-event publisher for Layer 2 (LangGraph).

COPY THIS SINGLE FILE into your Layer 2 package. It has no dependency on the rest
of agent_service. Only requirement: `pip install redis` and a REDIS_URL env var
(default redis://localhost:6379/0).

Channel contract (consumed by GET /research/{run_id}/stream):
    channel:  run:{run_id}:events
    message:  {"type": "step_started|step_completed|conflict_found|report_ready",
               "payload": {...}, "ts": "<iso8601>"}

How run_id reaches a node
-------------------------
Layer 3's AgentState (ticker, quarter, market_data, filings_data, news_data,
quant_data, errors) has NO run_id key. The decorator therefore looks for run_id in
this order and silently does nothing (never raises) if it finds none:
  1. state["run_id"] / state.run_id            (add `run_id: str` to AgentState - recommended)
  2. config["configurable"]["run_id"]          (graph.invoke(state, {"configurable": {"run_id": ...}}))
  3. the RUN_ID environment variable           (one process per run)
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional, Sequence

import redis as redis_sync

log = logging.getLogger("progress_events")

EventType = Literal["step_started", "step_completed", "conflict_found", "report_ready"]

# step name -> progress % reported when that step completes. Fill with YOUR node names via
# register_steps([...]); unknown steps simply report no percentage.
_STEP_PROGRESS: dict[str, int] = {}


def register_steps(ordered_node_names: Sequence[str], *, max_pct: int = 95) -> None:
    """Spread progress evenly over your real node names, e.g.
    register_steps(["market_data", "filings", "news", "quant", "synthesize"])"""
    n = len(ordered_node_names)
    for i, name in enumerate(ordered_node_names, start=1):
        _STEP_PROGRESS[name] = round(i / n * max_pct)


def channel_for(run_id: str) -> str:
    return f"run:{run_id}:events"


def _envelope(event_type: str, payload: dict[str, Any]) -> str:
    return json.dumps(
        {"type": event_type, "payload": payload, "ts": datetime.now(timezone.utc).isoformat()}, default=str
    )


_client: Optional[redis_sync.Redis] = None


def _redis() -> redis_sync.Redis:
    global _client
    if _client is None:
        _client = redis_sync.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _client


def publish_event_sync(run_id: str | None, event_type: EventType, payload: dict[str, Any] | None = None) -> bool:
    """Publish one event. Never raises: progress reporting must not break a research run."""
    if not run_id:
        return False
    try:
        _redis().publish(channel_for(str(run_id)), _envelope(event_type, payload or {}))
        return True
    except Exception as exc:
        log.warning("progress event not published (%s): %s", event_type, exc)
        return False


def _find_run_id(args: tuple, kwargs: dict) -> str | None:
    state = args[0] if args else kwargs.get("state")
    run_id = None
    if isinstance(state, dict):
        run_id = state.get("run_id")
    elif state is not None:
        run_id = getattr(state, "run_id", None)
    if not run_id:
        cfg = kwargs.get("config") or next((a for a in args[1:] if isinstance(a, dict) and "configurable" in a), None)
        if isinstance(cfg, dict):
            run_id = (cfg.get("configurable") or {}).get("run_id")
    return str(run_id or os.environ.get("RUN_ID") or "") or None


def with_progress_events(step_name: str) -> Callable:
    """Decorator for LangGraph nodes (sync or async). Emits step_started / step_completed and,
    if the node's returned dict contains a non-empty "conflicts" list, one conflict_found per item.

    LangGraph only hands `config` to nodes whose signature has a parameter literally named `config`.
    The wrapper therefore ALWAYS exposes one (so run_id can come from `configurable`), and only
    forwards it to your function if your function declared it too."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        orig_sig = inspect.signature(fn)
        accepts_config = "config" in orig_sig.parameters
        if accepts_config:
            new_sig = orig_sig
        else:
            new_sig = orig_sig.replace(
                parameters=[*orig_sig.parameters.values(),
                            inspect.Parameter("config", inspect.Parameter.KEYWORD_ONLY, default=None)]
            )

        def _done(run_id: str | None, result: Any) -> None:
            if isinstance(result, dict):
                for c in result.get("conflicts") or []:
                    publish_event_sync(run_id, "conflict_found", {"step": step_name, "conflict": c})
            payload: dict[str, Any] = {"step": step_name}
            if step_name in _STEP_PROGRESS:
                payload["progress_pct"] = _STEP_PROGRESS[step_name]
            publish_event_sync(run_id, "step_completed", payload)

        def _prep(args: tuple, kwargs: dict) -> tuple[str | None, dict]:
            run_id = _find_run_id(args, kwargs)
            call_kwargs = dict(kwargs)
            if not accepts_config:
                call_kwargs.pop("config", None)
            return run_id, call_kwargs

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def awrapper(*args: Any, **kwargs: Any) -> Any:
                run_id, call_kwargs = _prep(args, kwargs)
                await asyncio.to_thread(publish_event_sync, run_id, "step_started", {"step": step_name})
                result = await fn(*args, **call_kwargs)
                await asyncio.to_thread(_done, run_id, result)
                return result

            awrapper.__signature__ = new_sig  # type: ignore[attr-defined]
            return awrapper

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            run_id, call_kwargs = _prep(args, kwargs)
            publish_event_sync(run_id, "step_started", {"step": step_name})
            result = fn(*args, **call_kwargs)
            _done(run_id, result)
            return result

        wrapper.__signature__ = new_sig  # type: ignore[attr-defined]
        return wrapper

    return decorator


def publish_report_ready(run_id: str, summary: str = "") -> bool:
    """Call this AFTER the report has been saved to Neon (run_store.save_report)."""
    return publish_event_sync(run_id, "report_ready", {"run_id": str(run_id), "summary": summary})
