"""Quant sandbox: runs financial computations inside an E2B sandbox (30s timeout)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from pydantic import BaseModel, Field

from .common import ToolError, get_logger, guarded, log_event
from .market_data import FinancialPeriod

log = get_logger("quant_sandbox")

TIMEOUT_S = 30
_MARKER = "__SANDBOX_RESULT__"
_INPUT_PATH = "/home/user/input.json"

_PREAMBLE = f'''import json, math, statistics, sys
with open("{_INPUT_PATH}") as _f:
    DATA = json.load(_f)
result = None
'''
_EPILOGUE = f'''
try:
    print("\\n{_MARKER}" + json.dumps(result, default=str))
except Exception as _e:
    print("sandbox: result not JSON-serialisable: " + repr(_e), file=sys.stderr)
'''

# Pre-built template: expects DATA = {"periods": [...], "price": float|None, "market_cap": float|None}
METRICS_TEMPLATE = r'''
from datetime import date

periods = sorted(DATA["periods"], key=lambda p: p.get("end_date") or "")
price = DATA.get("price")
market_cap = DATA.get("market_cap")
notes = []

def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None

annual = [p for p in periods if (p.get("fiscal_period") or "").upper() == "FY"]
quarterly = [p for p in periods if (p.get("fiscal_period") or "").upper().startswith("Q")]

def years_between(a, b):
    return max((date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days / 365.25, 0.0)

def cagr(first, last, yrs):
    if first is None or last is None or yrs <= 0:
        return None
    if first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / yrs) - 1

def ttm(field, offset=0):
    """Sum of 4 quarters ending `offset` quarters back; falls back to latest annual value."""
    if len(quarterly) >= 4 + offset:
        sl = quarterly[len(quarterly) - 4 - offset: len(quarterly) - offset]
        vals = [num(p.get(field)) for p in sl]
        if all(v is not None for v in vals):
            return sum(vals)
    if offset == 0 and annual:
        return num(annual[-1].get(field))
    return None

def series_cagr(field, label):
    if len(annual) >= 2:
        f, l = annual[0], annual[-1]
        v = cagr(num(f.get(field)), num(l.get(field)), years_between(f["end_date"], l["end_date"]))
    elif len(quarterly) >= 8:
        v = cagr(ttm(field, 4), ttm(field, 0), 1.0)
        notes.append(label + " CAGR computed as TTM year-over-year (quarterly data)")
    else:
        v = None
    if v is None:
        notes.append(label + " CAGR unavailable (insufficient periods or non-positive endpoints)")
    return v

revenue_cagr = series_cagr("revenue", "revenue")
eps_field = "eps_diluted" if any(num(p.get("eps_diluted")) is not None for p in periods) else "eps_basic"
eps_cagr = series_cagr(eps_field, "EPS")

latest = periods[-1] if periods else {}

rev_ttm, oi_ttm, da_ttm = ttm("revenue"), ttm("operating_income"), ttm("depreciation_amortization")
ebitda_margin = None
if rev_ttm and oi_ttm is not None:
    if da_ttm is None:
        notes.append("EBITDA approximated by operating income (no D&A reported)")
    ebitda_margin = (oi_ttm + (da_ttm or 0)) / rev_ttm

pe_ratio = None
eps_ttm = ttm(eps_field)
if price and eps_ttm:
    if eps_ttm > 0:
        pe_ratio = price / eps_ttm
    else:
        notes.append("P/E not meaningful: non-positive TTM EPS")

debt_to_equity = None
equity = num(latest.get("equity"))
debt = num(latest.get("total_debt"))
if debt is None and num(latest.get("total_liabilities")) is not None:
    debt = num(latest.get("total_liabilities"))
    notes.append("debt/equity uses total liabilities (no debt line reported)")
if equity and equity > 0 and debt is not None:
    debt_to_equity = debt / equity
elif equity is not None and equity <= 0:
    notes.append("debt/equity not meaningful: non-positive equity")

fcf = fcf_yield = None
ocf, capex = ttm("operating_cash_flow"), ttm("capex")
if ocf is not None:
    if capex is None:
        notes.append("FCF approximated by operating cash flow (no capex reported)")
        fcf = ocf
    else:
        fcf = ocf - abs(capex)
    if market_cap:
        fcf_yield = fcf / market_cap
    else:
        notes.append("FCF yield unavailable: market cap not provided")

result = {
    "revenue_cagr": revenue_cagr, "eps_cagr": eps_cagr, "ebitda_margin": ebitda_margin,
    "pe_ratio": pe_ratio, "debt_to_equity": debt_to_equity, "fcf_yield": fcf_yield,
    "free_cash_flow": fcf, "periods_used": len(periods), "notes": notes,
}
'''


class SandboxError(ToolError):
    pass


class SandboxResult(BaseModel):
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_value: Any = None
    error: str | None = None
    timed_out: bool = False
    duration_ms: float = 0.0


class ComputedMetrics(BaseModel):
    revenue_cagr: float | None = None
    eps_cagr: float | None = None
    ebitda_margin: float | None = None
    pe_ratio: float | None = None
    debt_to_equity: float | None = None
    fcf_yield: float | None = None
    free_cash_flow: float | None = None
    periods_used: int = 0
    notes: list[str] = Field(default_factory=list)
    sandbox_duration_ms: float = 0.0


class CrossCheckResult(BaseModel):
    match: bool
    delta_pct: float
    flagged: bool
    claim_a: float
    claim_b: float
    source_a: str
    source_b: str
    tolerance: float


class QuantSandboxTool:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def _execute(self, code: str, data: dict[str, Any]) -> SandboxResult:
        from e2b_code_interpreter import AsyncSandbox

        started = time.perf_counter()
        sbx = None
        try:
            sbx = await AsyncSandbox.create(api_key=self._api_key, timeout=TIMEOUT_S + 60)
            await sbx.files.write(_INPUT_PATH, json.dumps(data, default=str))
            execution = await asyncio.wait_for(
                sbx.run_code(_PREAMBLE + "\n" + code + "\n" + _EPILOGUE, timeout=TIMEOUT_S),
                timeout=TIMEOUT_S + 10)
            stdout = "".join(execution.logs.stdout)
            stderr = "".join(execution.logs.stderr)
            return_value = None
            if _MARKER in stdout:
                head, _, tail = stdout.rpartition(_MARKER)
                stdout = head.rstrip("\n")
                try:
                    return_value = json.loads(tail.strip().splitlines()[0])
                except (json.JSONDecodeError, IndexError):
                    stderr += "\nsandbox: could not parse result payload"
            err = execution.error
            err_text = f"{err.name}: {err.value}\n{err.traceback}" if err else None
            return SandboxResult(success=err is None, stdout=stdout, stderr=stderr, return_value=return_value,
                                 error=err_text, duration_ms=(time.perf_counter() - started) * 1000)
        except (asyncio.TimeoutError, TimeoutError):
            log_event(log, logging.ERROR, "sandbox_timeout", timeout_s=TIMEOUT_S)
            return SandboxResult(success=False, timed_out=True, error=f"execution exceeded {TIMEOUT_S}s",
                                 duration_ms=(time.perf_counter() - started) * 1000)
        except Exception as exc:  # noqa: BLE001 - e2b raises its own timeout types too
            timed_out = "timeout" in repr(exc).lower() or "timed out" in str(exc).lower()
            log_event(log, logging.ERROR, "sandbox_error", error=repr(exc), timed_out=timed_out)
            return SandboxResult(success=False, timed_out=timed_out, error=repr(exc),
                                 duration_ms=(time.perf_counter() - started) * 1000)
        finally:
            if sbx is not None:
                try:
                    await sbx.kill()
                except Exception as exc:  # noqa: BLE001
                    log_event(log, logging.WARNING, "sandbox_kill_failed", error=repr(exc))

    @guarded("e2b.run_financial_computation", SandboxError)
    async def run_financial_computation(self, code: str, data: dict[str, Any]) -> SandboxResult:
        """`data` is exposed to your code as DATA; assign JSON-serialisable output to `result`."""
        res = await self._execute(code, data)
        log_event(log, logging.INFO, "sandbox_run", success=res.success, timed_out=res.timed_out,
                  duration_ms=round(res.duration_ms, 1))
        return res

    @guarded("e2b.compute_metrics", SandboxError)
    async def compute_metrics(self, financials: list[FinancialPeriod], price: float | None = None,
                              market_cap: float | None = None) -> ComputedMetrics:
        if not financials:
            raise SandboxError("compute_metrics requires at least one FinancialPeriod")
        data = {"periods": [f.model_dump(mode="json") for f in financials],
                "price": price, "market_cap": market_cap}
        res = await self._execute(METRICS_TEMPLATE, data)
        if not res.success or not isinstance(res.return_value, dict):
            raise SandboxError(f"metrics computation failed: {res.error or res.stderr or 'no result'}")
        return ComputedMetrics(**res.return_value, sandbox_duration_ms=res.duration_ms)

    @guarded("quant.cross_check_numbers", SandboxError)
    async def cross_check_numbers(self, claim_a: float, claim_b: float, source_a: str, source_b: str,
                                  tolerance: float = 0.05) -> CrossCheckResult:
        """Deterministic local arithmetic (no sandbox needed). tolerance is a fraction (0.05 = 5%).
        delta is relative to the larger magnitude, expressed in percent."""
        a, b = float(claim_a), float(claim_b)
        denom = max(abs(a), abs(b))
        ratio = 0.0 if denom == 0 else abs(a - b) / denom
        flagged = ratio > tolerance
        return CrossCheckResult(match=not flagged, delta_pct=round(ratio * 100, 4), flagged=flagged,
                                claim_a=a, claim_b=b, source_a=source_a, source_b=source_b,
                                tolerance=tolerance)


# --------------------------------------------------------------------------- smoke test
async def _demo() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    tool = QuantSandboxTool(os.environ.get("E2B_API_KEY", ""))
    print("cross_check:", (await tool.cross_check_numbers(100.0, 103.0, "10-K", "Polygon")).model_dump())
    print("cross_check flagged:", (await tool.cross_check_numbers(100.0, 120.0, "10-K", "Polygon")).flagged)
    if not os.environ.get("E2B_API_KEY"):
        print("E2B_API_KEY not set — skipping sandbox tests")
        return
    r = await tool.run_financial_computation("result = {'sum': sum(DATA['xs'])}\nprint('hi')", {"xs": [1, 2, 3]})
    print("sandbox:", r.model_dump())
    periods = [
        FinancialPeriod(ticker="TEST", fiscal_period="FY", end_date=f"{y}-12-31", revenue=100.0 * 1.1 ** i,
                        operating_income=20.0 * 1.1 ** i, eps_diluted=1.0 * 1.15 ** i, equity=500.0,
                        total_debt=200.0, operating_cash_flow=30.0, capex=-10.0)
        for i, y in enumerate(range(2020, 2025))
    ]
    m = await tool.compute_metrics(periods, price=50.0, market_cap=5000.0)
    print("metrics:", m.model_dump())


if __name__ == "__main__":
    asyncio.run(_demo())
