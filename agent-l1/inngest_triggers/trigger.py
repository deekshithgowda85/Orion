"""Inngest functions that start Temporal workflows.

* ``on_research_requested`` - event ``market-research/query.submitted`` (webhook)
* ``portfolio_daily_scan``  - cron 07:00 UTC Mon-Fri (also fires on the
  ``market-research/portfolio.daily-scan`` event for manual runs)
"""
from datetime import datetime, timezone
from typing import Any

import inngest
from pydantic import ValidationError

from config import DAILY_SCAN_CRON, EVENT_DAILY_SCAN, EVENT_QUERY_SUBMITTED, get_settings
from models.workflow_models import ResearchRequest
from temporal_client import start_research

_settings = get_settings()

inngest_client = inngest.Inngest(
    app_id="market-research-agent",
    event_key=_settings.inngest_event_key,
    signing_key=_settings.inngest_signing_key,
    is_production=not _settings.inngest_dev,
)


@inngest_client.create_function(
    fn_id="on-research-requested",
    trigger=inngest.TriggerEvent(event=EVENT_QUERY_SUBMITTED),
    retries=3,
)
async def on_research_requested(ctx: inngest.Context) -> dict[str, Any]:
    """Validate a submitted query and start a ResearchWorkflow."""
    try:
        request = ResearchRequest.model_validate(ctx.event.data)
    except ValidationError as exc:
        raise inngest.NonRetriableError(message=f"invalid research request: {exc}") from exc

    async def _start() -> dict[str, Any]:
        return await start_research(request)

    return await ctx.step.run("start-research-workflow", _start)


@inngest_client.create_function(
    fn_id="portfolio-daily-scan",
    trigger=[
        inngest.TriggerCron(cron=DAILY_SCAN_CRON),
        inngest.TriggerEvent(event=EVENT_DAILY_SCAN),
    ],
    retries=3,
)
async def portfolio_daily_scan(ctx: inngest.Context) -> dict[str, Any]:
    """Start one ``daily_scan`` workflow per configured portfolio ticker."""
    settings = get_settings()
    scan_date = datetime.fromtimestamp(ctx.event.ts / 1000, tz=timezone.utc).date().isoformat()

    async def _fan_out() -> dict[str, Any]:
        started: list[dict[str, Any]] = []
        for ticker in settings.daily_scan_tickers:
            request = ResearchRequest(
                ticker=ticker,
                query=(
                    f"Daily portfolio scan for {ticker}: overnight price action, "
                    "material news, new filings and emerging risks."
                ),
                workflow_type="daily_scan",
                tenant_id=settings.daily_scan_tenant_id,
                run_id=f"scan-{scan_date}-{ticker}".replace(".", "-"),  # deterministic => idempotent
            )
            started.append({"ticker": ticker, **await start_research(request)})
        return {"scan_date": scan_date, "workflows": started}

    return await ctx.step.run("start-daily-scan-workflows", _fan_out)


FUNCTIONS = [on_research_requested, portfolio_daily_scan]
