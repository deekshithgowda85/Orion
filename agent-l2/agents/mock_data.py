"""Synthetic fixtures for the standalone ``__main__`` demos and tests.

All companies, numbers and URLs here are FICTIONAL test data (ticker ACME).
"""
from typing import Any

from agents.state import AgentState, initial_state
from models.workflow_models import ResearchRequest, SubGoal

MOCK_REQUEST = ResearchRequest(
    ticker="ACME",
    query="Assess ACME's latest fiscal-year performance, filing disclosures and recent news risk.",
    workflow_type="deep_audit",
    tenant_id="demo-tenant",
    run_id="mock-run-1",
)

MOCK_RAW: dict[str, dict[str, Any]] = {
    "market_data": {
        "sources": [{"url": "https://api.examplefin.test/v1/acme/financials", "title": "ExampleFin - ACME financials"}],
        "content": {"symbol": "ACME", "fiscal_year": "FY2025", "revenue_usd_millions": 12500,
                    "net_income_usd_millions": 1900, "eps_diluted_usd": 3.12, "pe_ratio_ttm": 18.4},
    },
    "filings": {
        "sources": [{"url": "https://www.sec.gov/Archives/edgar/data/0000000/acme-10k-fy2025.htm", "title": "ACME 10-K FY2025"}],
        "content": ("[Page 42] Total revenue for fiscal 2025 was $11.9 billion, up 6% from fiscal 2024.\n"
                    "[Page 44] Net income for fiscal 2025 was $1.9 billion.\n"
                    "[Page 18] Item 1A: A pending regulatory inquiry could result in fines or product changes."),
    },
    "news": {
        "sources": [
            {"url": "https://news.example.test/acme-guidance", "title": "ACME raises full-year guidance"},
            {"url": "https://news.example.test/acme-inquiry", "title": "Regulator opens inquiry into ACME"},
        ],
        "content": [
            {"headline": "ACME raises full-year guidance", "date": "2026-10-28",
             "text": "ACME lifted its outlook citing strong demand. Analysts reacted positively."},
            {"headline": "Regulator opens inquiry into ACME", "date": "2026-11-02",
             "text": "A regulator opened an inquiry into ACME's pricing practices, creating uncertainty."},
        ],
    },
}


async def mock_get_tool_output(goal: SubGoal, ticker: str, query: str, run_id: str) -> dict[str, Any]:
    """Drop-in replacement for ``tool_hook.get_tool_output`` returning fixtures."""
    return MOCK_RAW.get(goal.agent_type, {})


def mock_state() -> AgentState:
    """Return a fresh state for the mock request."""
    return initial_state(MOCK_REQUEST)
