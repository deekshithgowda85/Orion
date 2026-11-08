"""Scheduling support.

DESIGN (replaces the earlier version, which called Inngest REST endpoints that do not exist):

* Neon (`workflow_schedules`) is the source of truth for schedules.
* Execution: ANY clock can call `POST /internal/schedules/run-due` once a minute with the
  `X-Internal-Key` header (see routes/internal.py). The recommended clock is an Inngest cron function
  (`* * * * *`) - see LAYER4_INTEGRATION.md - but Windows Task Scheduler / cron / `curl` work too.
* Notification (optional): when INNGEST_EVENT_KEY is set, create/delete also send a real Inngest
  Event API event (`research/schedule.created` / `research/schedule.deleted`) so Inngest functions
  can react. If the key is missing the schedule is still stored and the API response carries a
  `warning` - it does not fail.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from config import get_settings

log = logging.getLogger("inngest")


class InngestError(Exception):
    pass


def enabled() -> bool:
    return bool(get_settings().inngest_event_key)


async def send_event(name: str, data: dict[str, Any]) -> None:
    """POST to the Inngest Event API: https://inn.gs/e/<event key>. Raises InngestError."""
    s = get_settings()
    if not s.inngest_event_key:
        raise InngestError("INNGEST_EVENT_KEY is not set")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{s.inngest_event_url}/{s.inngest_event_key}",
                json={"name": name, "data": data, "id": str(uuid.uuid4())},
            )
    except httpx.HTTPError as exc:
        raise InngestError(f"Inngest unreachable: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        raise InngestError(f"Inngest Event API returned HTTP {resp.status_code}")
