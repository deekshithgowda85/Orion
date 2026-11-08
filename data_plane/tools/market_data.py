"""Polygon market data tool (async wrapper over the sync polygon-api-client)."""
from __future__ import annotations

import asyncio
import itertools
import logging
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal, TypeVar

import redis.asyncio as aioredis
from polygon import RESTClient
from pydantic import BaseModel, Field, TypeAdapter

from .common import ToolError, g, get_logger, guarded, log_event, to_float, with_retry

log = get_logger("market_data")
T = TypeVar("T")

TTL_SNAPSHOT = 60
TTL_FINANCIALS = 3600
TTL_NEWS = 300
TTL_OPTIONS = 60


class MarketDataError(ToolError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- models
class StockSnapshot(BaseModel):
    ticker: str
    price: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    vwap: float | None = None
    prev_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    updated_ns: int | None = None
    fetched_at: datetime = Field(default_factory=_now)


class FinancialPeriod(BaseModel):
    ticker: str
    fiscal_year: str | None = None
    fiscal_period: str | None = None  # "FY", "Q1".."Q4"
    start_date: str | None = None
    end_date: str | None = None
    filing_date: str | None = None
    revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    diluted_shares: float | None = None
    depreciation_amortization: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_debt: float | None = None  # long-term debt as reported by Polygon (may be None)
    equity: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None


class OptionContract(BaseModel):
    ticker: str
    contract_type: Literal["call", "put"] | None = None
    strike: float | None = None
    expiration: str | None = None
    open_interest: float | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    last_price: float | None = None
    volume: float | None = None
    bid: float | None = None
    ask: float | None = None


class OptionsChain(BaseModel):
    underlying: str
    underlying_price: float | None = None
    contracts: list[OptionContract]
    truncated: bool = False
    fetched_at: datetime = Field(default_factory=_now)

    def summary(self) -> dict[str, Any]:
        calls = [c for c in self.contracts if c.contract_type == "call"]
        puts = [c for c in self.contracts if c.contract_type == "put"]
        call_oi = sum(c.open_interest or 0 for c in calls)
        put_oi = sum(c.open_interest or 0 for c in puts)
        ivs = [c.implied_volatility for c in self.contracts if c.implied_volatility]
        return {
            "contracts": len(self.contracts),
            "calls": len(calls),
            "puts": len(puts),
            "call_open_interest": call_oi,
            "put_open_interest": put_oi,
            "put_call_oi_ratio": round(put_oi / call_oi, 4) if call_oi else None,
            "avg_implied_volatility": round(sum(ivs) / len(ivs), 4) if ivs else None,
            "expirations": sorted({c.expiration for c in self.contracts if c.expiration})[:8],
            "truncated": self.truncated,
        }


class NewsItem(BaseModel):
    id: str | None = None
    title: str
    author: str | None = None
    publisher: str | None = None
    published_utc: datetime | None = None
    article_url: str | None = None
    description: str | None = None
    tickers: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    sentiment: str | None = None
    sentiment_reasoning: str | None = None


_SNAP = TypeAdapter(StockSnapshot)
_FIN = TypeAdapter(list[FinancialPeriod])
_OPT = TypeAdapter(OptionsChain)
_NEWS = TypeAdapter(list[NewsItem])


def _dp(section: Any, *names: str) -> float | None:
    """Pull `.value` from a Polygon financial data point (dict or object); first name that exists wins."""
    for name in names:
        dp = g(section, name)
        if dp is not None:
            val = to_float(g(dp, "value"))
            if val is not None:
                return val
    return None


# --------------------------------------------------------------------------- tool
class MarketDataTool:
    def __init__(self, api_key: str, redis: aioredis.Redis | None = None) -> None:
        try:
            # retries=0: backoff is handled here so retries don't multiply with urllib3's own.
            self._client = RESTClient(api_key=api_key, retries=0)
        except TypeError:
            self._client = RESTClient(api_key=api_key)
        self._redis = redis

    # ---- plumbing
    async def _call(self, op: str, fn: Callable[..., Any], *args: Any, ticker: str = "", **kwargs: Any) -> Any:
        async def attempt() -> Any:
            return await asyncio.to_thread(fn, *args, **kwargs)

        return await with_retry(attempt, op=op, logger=log, max_retries=3, base_delay=1.0,
                                ctx={"ticker": ticker})

    async def _cached(self, key: str, ttl: int, adapter: TypeAdapter, fetch: Callable[[], Awaitable[T]]) -> T:
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                if raw:
                    return adapter.validate_json(raw)
            except Exception as exc:  # noqa: BLE001 - cache must never break the fetch path
                log_event(log, logging.WARNING, "cache_read_failed", key=key, error=repr(exc))
        value = await fetch()
        if self._redis is not None:
            try:
                await self._redis.set(key, adapter.dump_json(value), ex=ttl)
            except Exception as exc:  # noqa: BLE001
                log_event(log, logging.WARNING, "cache_write_failed", key=key, error=repr(exc))
        return value

    # ---- sync workers (run in threads)
    def _snapshot_sync(self, ticker: str) -> StockSnapshot:
        snap = self._client.get_snapshot_ticker("stocks", ticker)
        day, prev, last = g(snap, "day"), g(snap, "prev_day"), g(snap, "last_trade")
        price = to_float(g(last, "price")) or to_float(g(day, "close")) or to_float(g(prev, "close"))
        if price is None:
            raise MarketDataError(f"no price available for {ticker}")
        return StockSnapshot(
            ticker=ticker,
            price=price,
            open=to_float(g(day, "open")),
            high=to_float(g(day, "high")),
            low=to_float(g(day, "low")),
            close=to_float(g(day, "close")),
            volume=to_float(g(day, "volume")),
            vwap=to_float(g(day, "vwap")),
            prev_close=to_float(g(prev, "close")),
            change=to_float(g(snap, "todays_change")),
            change_pct=to_float(g(snap, "todays_change_perc")),
            updated_ns=int(g(snap, "updated")) if g(snap, "updated") else None,
        )

    def _financials_sync(self, ticker: str, limit: int, timeframe: str) -> list[FinancialPeriod]:
        it = self._client.vx.list_stock_financials(
            ticker=ticker, timeframe=timeframe, limit=limit,
            order="desc", sort="period_of_report_date",
        )
        out: list[FinancialPeriod] = []
        for item in itertools.islice(it, limit):
            fin = g(item, "financials")
            if fin is None:
                continue
            inc, bal, cf = g(fin, "income_statement"), g(fin, "balance_sheet"), g(fin, "cash_flow_statement")
            out.append(FinancialPeriod(
                ticker=ticker,
                fiscal_year=str(g(item, "fiscal_year")) if g(item, "fiscal_year") else None,
                fiscal_period=g(item, "fiscal_period"),
                start_date=g(item, "start_date"),
                end_date=g(item, "end_date"),
                filing_date=g(item, "filing_date"),
                revenue=_dp(inc, "revenues"),
                operating_income=_dp(inc, "operating_income_loss"),
                net_income=_dp(inc, "net_income_loss", "net_income_loss_attributable_to_parent"),
                eps_basic=_dp(inc, "basic_earnings_per_share"),
                eps_diluted=_dp(inc, "diluted_earnings_per_share"),
                diluted_shares=_dp(inc, "diluted_average_shares"),
                depreciation_amortization=_dp(inc, "depreciation_and_amortization",
                                              "depreciation_depletion_and_amortization")
                or _dp(cf, "depreciation_and_amortization", "depreciation_depletion_and_amortization"),
                total_assets=_dp(bal, "assets"),
                total_liabilities=_dp(bal, "liabilities"),
                total_debt=_dp(bal, "long_term_debt"),
                equity=_dp(bal, "equity", "equity_attributable_to_parent"),
                operating_cash_flow=_dp(cf, "net_cash_flow_from_operating_activities"),
                capex=_dp(cf, "payments_to_acquire_property_plant_and_equipment", "capital_expenditures"),
            ))
        return out

    def _options_sync(self, ticker: str, max_contracts: int) -> OptionsChain:
        it = self._client.list_snapshot_options_chain(ticker, params={"limit": 250})
        contracts: list[OptionContract] = []
        underlying_price: float | None = None
        count = 0
        for c in itertools.islice(it, max_contracts + 1):
            count += 1
            if count > max_contracts:
                break
            d, greeks, day, quote = g(c, "details"), g(c, "greeks"), g(c, "day"), g(c, "last_quote")
            ctype = g(d, "contract_type")
            if underlying_price is None:
                underlying_price = to_float(g(g(c, "underlying_asset"), "price"))
            contracts.append(OptionContract(
                ticker=g(d, "ticker") or "",
                contract_type=ctype if ctype in ("call", "put") else None,
                strike=to_float(g(d, "strike_price")),
                expiration=str(g(d, "expiration_date")) if g(d, "expiration_date") else None,
                open_interest=to_float(g(c, "open_interest")),
                implied_volatility=to_float(g(c, "implied_volatility")),
                delta=to_float(g(greeks, "delta")),
                gamma=to_float(g(greeks, "gamma")),
                theta=to_float(g(greeks, "theta")),
                vega=to_float(g(greeks, "vega")),
                last_price=to_float(g(day, "close")),
                volume=to_float(g(day, "volume")),
                bid=to_float(g(quote, "bid")),
                ask=to_float(g(quote, "ask")),
            ))
        return OptionsChain(underlying=ticker, underlying_price=underlying_price,
                            contracts=contracts, truncated=count > max_contracts)

    def _news_sync(self, ticker: str, limit: int) -> list[NewsItem]:
        it = self._client.list_ticker_news(ticker=ticker, limit=min(limit, 1000),
                                           order="desc", sort="published_utc")
        out: list[NewsItem] = []
        for n in itertools.islice(it, limit):
            sentiment = reasoning = None
            for ins in g(n, "insights") or []:
                if g(ins, "ticker") == ticker:
                    sentiment, reasoning = g(ins, "sentiment"), g(ins, "sentiment_reasoning")
                    break
            pub = g(n, "publisher")
            out.append(NewsItem(
                id=g(n, "id"),
                title=g(n, "title") or "(untitled)",
                author=g(n, "author"),
                publisher=g(pub, "name") if pub is not None else None,
                published_utc=g(n, "published_utc"),
                article_url=g(n, "article_url"),
                description=g(n, "description"),
                tickers=list(g(n, "tickers") or []),
                keywords=list(g(n, "keywords") or []),
                sentiment=sentiment,
                sentiment_reasoning=reasoning,
            ))
        return out

    # ---- public async API
    @guarded("polygon.get_stock_snapshot", MarketDataError)
    async def get_stock_snapshot(self, ticker: str) -> StockSnapshot:
        t = ticker.upper().strip()

        async def fetch() -> StockSnapshot:
            return await self._call("polygon.snapshot", self._snapshot_sync, t, ticker=t)

        return await self._cached(f"market:snapshot:{t}", TTL_SNAPSHOT, _SNAP, fetch)

    @guarded("polygon.get_financials", MarketDataError)
    async def get_financials(self, ticker: str, limit: int = 8,
                             timeframe: Literal["annual", "quarterly"] = "annual") -> list[FinancialPeriod]:
        """Most recent period first."""
        t = ticker.upper().strip()

        async def fetch() -> list[FinancialPeriod]:
            return await self._call("polygon.financials", self._financials_sync, t, limit, timeframe, ticker=t)

        return await self._cached(f"market:financials:{t}:{timeframe}:{limit}", TTL_FINANCIALS, _FIN, fetch)

    @guarded("polygon.get_options_chain", MarketDataError)
    async def get_options_chain(self, ticker: str, max_contracts: int = 500) -> OptionsChain:
        t = ticker.upper().strip()

        async def fetch() -> OptionsChain:
            return await self._call("polygon.options_chain", self._options_sync, t, max_contracts, ticker=t)

        return await self._cached(f"market:options:{t}:{max_contracts}", TTL_OPTIONS, _OPT, fetch)

    @guarded("polygon.get_news", MarketDataError)
    async def get_news(self, ticker: str, limit: int = 20) -> list[NewsItem]:
        t = ticker.upper().strip()

        async def fetch() -> list[NewsItem]:
            return await self._call("polygon.news", self._news_sync, t, limit, ticker=t)

        return await self._cached(f"market:news:{t}:{limit}", TTL_NEWS, _NEWS, fetch)


# --------------------------------------------------------------------------- smoke test
async def _demo() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        print("POLYGON_API_KEY not set — skipping live test")
        return
    redis = aioredis.from_url(os.environ["REDIS_URL"]) if os.environ.get("REDIS_URL") else None
    tool = MarketDataTool(key, redis)
    snap, fin, opts, news = await asyncio.gather(
        tool.get_stock_snapshot("AAPL"), tool.get_financials("AAPL", limit=4),
        tool.get_options_chain("AAPL", max_contracts=100), tool.get_news("AAPL", limit=5),
        return_exceptions=True,
    )
    for name, res in (("snapshot", snap), ("financials", fin), ("options", opts), ("news", news)):
        if isinstance(res, Exception):
            print(f"{name}: ERROR {res}")
        elif name == "options":
            print(name, res.summary())
        elif name == "snapshot":
            print(name, res.model_dump_json())
        else:
            print(name, f"{len(res)} items; first: {res[0].model_dump_json()[:200] if res else None}")
    if redis is not None:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(_demo())
