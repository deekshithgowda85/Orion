"""Tiny CLI to exercise the workflow without Inngest.

    python submit.py start --ticker AAPL --query "Audit AAPL services margins" --type deep_audit
    python submit.py approve <workflow_id> [--reject]
    python submit.py stage <workflow_id>
"""
import argparse
import asyncio

from config import workflow_id_for
from models.workflow_models import ApprovalDecision, ResearchRequest
from temporal_client import connect, start_research


async def _main() -> None:
    """Parse CLI arguments and run the chosen sub-command."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start")
    p_start.add_argument("--ticker", required=True)
    p_start.add_argument("--query", required=True)
    p_start.add_argument("--type", dest="wtype", default="deep_audit",
                         choices=["deep_audit", "daily_scan", "earnings_pulse"])
    p_start.add_argument("--tenant", default="demo-tenant")

    p_appr = sub.add_parser("approve")
    p_appr.add_argument("workflow_id")
    p_appr.add_argument("--reject", action="store_true")
    p_appr.add_argument("--reviewer", default="cli-user")

    p_stage = sub.add_parser("stage")
    p_stage.add_argument("workflow_id")

    args = parser.parse_args()
    client = await connect()

    if args.cmd == "start":
        request = ResearchRequest(ticker=args.ticker, query=args.query,
                                  workflow_type=args.wtype, tenant_id=args.tenant)
        print(await start_research(request, client))
        print("workflow_id =", workflow_id_for(request.tenant_id, request.run_id))
    elif args.cmd == "approve":
        handle = client.get_workflow_handle(args.workflow_id)
        await handle.signal("approve_report",
                            ApprovalDecision(approved=not args.reject, reviewer=args.reviewer))
        print("signal sent")
    else:
        handle = client.get_workflow_handle(args.workflow_id)
        print(await handle.query("current_stage"))


if __name__ == "__main__":
    asyncio.run(_main())
