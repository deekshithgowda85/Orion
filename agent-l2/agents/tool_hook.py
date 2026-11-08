"""Layer 3 injection point for raw tool output.

Layer 2 never fetches data. The parallel executor calls
:func:`get_tool_output` for every market_data / filings / news goal.
Layer 3 replaces the body of this function (or monkey-patches it) with real
tool calls.

Contract - return a dict shaped like::

    {
      "sources": [{"url": "https://...", "title": "...", "publisher": "...", "published_at": "..."}],
      "content": "<text>" | {...} | [...]      # raw payload to extract facts from
    }

An empty dict means "no data": executors then return nothing instead of guessing.
"""
from typing import Any

from models.workflow_models import SubGoal


async def get_tool_output(goal: SubGoal, ticker: str, query: str, run_id: str) -> dict[str, Any]:
    """Return raw tool output for ``goal``."""
    # TODO: Layer 3 injects real tool output here
    return {}
