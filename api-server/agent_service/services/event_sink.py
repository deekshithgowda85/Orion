"""Background task: mirror Layer 2 progress events from Redis into Neon.

Layer 2 only publishes to `run:{run_id}:events`; this sink turns step_started / step_completed
into `current_step` / `progress_pct` updates so GET /research/{id}/status works without Layer 1/2
needing database access for progress. (Saving the final report is still done by Layer 1/2 through
integration/run_store.py.)
"""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from db import queries

log = logging.getLogger("event_sink")


async def _handle(channel: str, raw: str) -> None:
    parts = channel.split(":")
    if len(parts) != 3 or parts[0] != "run":
        return
    try:
        run_id = UUID(parts[1])
        evt = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return
    payload = evt.get("payload") or {}
    etype = evt.get("type")
    if etype == "step_started":
        await queries.touch_run_step_by_id(run_id, payload.get("step"), None)
    elif etype == "step_completed":
        pct = payload.get("progress_pct")
        await queries.touch_run_step_by_id(run_id, payload.get("step"), pct if isinstance(pct, int) else None)


async def run_event_sink(app) -> None:
    backoff = 1.0
    while True:
        pubsub = None
        try:
            pubsub = app.state.redis.pubsub()
            await pubsub.psubscribe("run:*:events")
            backoff = 1.0
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "pmessage":
                    try:
                        await _handle(msg["channel"], msg["data"])
                    except Exception:
                        log.exception("event sink could not apply event")
        except asyncio.CancelledError:
            if pubsub is not None:
                try:
                    await pubsub.aclose()
                except Exception:
                    pass
            raise
        except Exception:
            log.warning("event sink lost Redis connection; retrying in %.0fs", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
