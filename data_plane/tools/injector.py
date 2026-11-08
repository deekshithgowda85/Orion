"""Layer 2 integration: LangGraph nodes that run BEFORE each executor and inject real tool output.

State keys written (map these to the placeholder dicts marked `# TODO: Layer 3 injects real tool output here`):
    market_data, filings_data, news_data, quant_data, errors
State keys read: ticker, run_id, tenant_id, (optional) quarter.

Raw filings / scraped pages are NEVER put into state: they are chunked into the vector store and
state only carries compact metadata + retrieval handles (use VectorStore.similarity_search on demand).
"""
from __future__ import annotations

import asyncio
import logging
import operator
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Awaitable, Callable, TypedDict

from .common import ToolError, get_logger, log_event
from .market_data import FinancialPeriod
from .registry import ToolRegistry

log = get_logger("injector")


class AgentState(TypedDict, total=False):
    """Minimal contract. Replace with (or extend from) Layer 2's AgentState — keys are additive."""
    run_id: str
    tenant_id: str
    ticker: str
    quarter: str
    market_data: dict[str, Any]
    filings_data: dict[str, Any]
    news_data: dict[str, Any]
    quant_data: dict[str, Any]
    # Reducer: parallel injector nodes can all report errors in one step. Nodes return ONLY their new errors.
    errors: Annotated[list[dict[str, Any]], operator.add]


NodeFn = Callable[[AgentState], Awaitable[AgentState]]
_PREVIEW = 300
_NEWS_SCRAPE_TOP_N = 3


def _err(source: str, exc: BaseException) -> dict[str, Any]:
    return {"source": source, "error_type": type(exc).__name__, "message": str(exc)[:500],
            "at": datetime.now(timezone.utc).isoformat()}


def _status(ok: bool, errors: list[dict[str, Any]]) -> str:
    return "ok" if not errors else ("partial" if ok else "error")


def _require(state: AgentState, *keys: str) -> tuple[str, ...]:
    missing = [k for k in keys if not state.get(k)]
    if missing:
        raise ToolError(f"state is missing required keys: {missing}")
    return tuple(str(state[k]) for k in keys)


def scan_todo_markers(root: str | Path) -> list[tuple[str, int, str]]:
    """Report every `# TODO: Layer 3` placeholder in Layer 2's source (file, line, text)."""
    hits: list[tuple[str, int, str]] = []
    for path in Path(root).rglob("*.py"):
        for i, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if re.search(r"#\s*TODO:\s*Layer\s*3", line, re.I):
                hits.append((str(path), i, line.strip()))
    return hits


class ToolInjector:
    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry

    @property
    def reg(self) -> ToolRegistry:
        return self._registry or ToolRegistry.instance()

    # ------------------------------------------------------------------ market data executor
    async def inject_market_data(self, state: AgentState) -> AgentState:
        ticker, run_id = _require(state, "ticker", "run_id")
        market = self.reg.get_market_tool()
        errors: list[dict[str, Any]] = []
        snap, fin, opts = await asyncio.gather(
            market.get_stock_snapshot(ticker), market.get_financials(ticker, limit=8),
            market.get_options_chain(ticker), return_exceptions=True)

        data: dict[str, Any] = {"ticker": ticker, "fetched_at": datetime.now(timezone.utc).isoformat()}
        for name, res in (("snapshot", snap), ("financials", fin), ("options", opts)):
            if isinstance(res, BaseException):
                errors.append(_err(f"market_data.{name}", res))
                data[name] = None
        if not isinstance(snap, BaseException):
            data["snapshot"] = snap.model_dump(mode="json")
        if not isinstance(fin, BaseException):
            data["financials"] = [f.model_dump(mode="json") for f in fin]
        if not isinstance(opts, BaseException):
            data["options_summary"] = opts.summary()
        data["status"] = _status(snap is not None and not isinstance(snap, BaseException), errors)

        await self._stash(run_id, "market_data", data)
        return self._merge(state, errors, market_data=data)

    # ------------------------------------------------------------------ filings executor
    async def inject_filings_data(self, state: AgentState) -> AgentState:
        ticker, run_id, tenant_id = _require(state, "ticker", "run_id", "tenant_id")
        sec, vs = self.reg.get_filings_tool(), self.reg.get_vector_store()
        errors: list[dict[str, Any]] = []

        forms = ("10-K", "10-Q", "8-K")
        found = await asyncio.gather(
            *(sec.search_filings(ticker, f, limit=5 if f == "8-K" else 3) for f in forms),
            return_exceptions=True)
        filings: dict[str, list[dict[str, Any]]] = {}
        for form, res in zip(forms, found):
            if isinstance(res, BaseException):
                errors.append(_err(f"filings.search.{form}", res))
                filings[form] = []
            else:
                filings[form] = [m.model_dump(mode="json") for m in res]

        async def process(form: str, meta: dict[str, Any]) -> list[dict[str, Any]]:
            acc = meta["accession_number"]
            text = await sec.download_filing(acc)
            parsed = await sec.parse_filing_with_llama(
                text, ["MD&A", "Risk Factors", "Financial Statements"], form_type=form, accession_number=acc)
            del text  # raw filing never leaves this function
            out: list[dict[str, Any]] = []
            for name, section in parsed.sections.items():
                chunks = await vs.ingest_text(section.text, {
                    "ticker": ticker, "kind": "filing", "form_type": form, "accession_number": acc,
                    "section": name, "start_page": section.start_page, "end_page": section.end_page,
                    "filing_date": meta.get("filing_date")}, run_id, tenant_id)
                out.append({"form_type": form, "accession_number": acc, "section": name,
                            "pages": [section.start_page, section.end_page], "chars": section.char_count,
                            "chunks": chunks, "preview": section.text[:_PREVIEW], "parser": parsed.parser})
            for m in parsed.missing_sections:
                errors.append({"source": f"filings.parse.{form}", "error_type": "SectionMissing",
                               "message": f"{m} not found in {acc}",
                               "at": datetime.now(timezone.utc).isoformat()})
            return out

        targets = [(f, filings[f][0]) for f in ("10-K", "10-Q") if filings.get(f)]
        results = await asyncio.gather(*(process(f, m) for f, m in targets), return_exceptions=True)
        parsed_summary: list[dict[str, Any]] = []
        for (form, _), res in zip(targets, results):
            if isinstance(res, BaseException):
                errors.append(_err(f"filings.process.{form}", res))
            else:
                parsed_summary.extend(res)

        past: list[dict[str, Any]] = []
        try:
            past = [{"run_id": c.run_id, "created_at": c.created_at.isoformat() if c.created_at else None,
                     "text": c.chunk_text[:800]} for c in await vs.get_past_findings(ticker, tenant_id)]
        except Exception as exc:  # noqa: BLE001
            errors.append(_err("filings.past_findings", exc))

        data = {"ticker": ticker, "filings": filings, "parsed_sections": parsed_summary,
                "past_findings": past,
                "retrieval": {"run_id": run_id, "tenant_id": tenant_id, "metadata_filter": {"kind": "filing"}},
                "status": _status(bool(parsed_summary or any(filings.values())), errors)}
        await self._stash(run_id, "filings_data", data)
        return self._merge(state, errors, filings_data=data)

    # ------------------------------------------------------------------ news executor
    async def inject_news_data(self, state: AgentState) -> AgentState:
        ticker, run_id, tenant_id = _require(state, "ticker", "run_id", "tenant_id")
        market, scraper, vs = self.reg.get_market_tool(), self.reg.get_scraper_tool(), self.reg.get_vector_store()
        errors: list[dict[str, Any]] = []

        try:
            news = await market.get_news(ticker, limit=20)
        except Exception as exc:  # noqa: BLE001
            errors.append(_err("news.polygon", exc))
            news = []

        async def scrape_and_store(item) -> dict[str, Any]:
            page = await scraper.scrape_url(item.article_url)
            n = await vs.ingest_text(page.markdown, {
                "ticker": ticker, "kind": "news", "url": item.article_url, "title": item.title,
                "publisher": item.publisher,
                "published_utc": item.published_utc.isoformat() if item.published_utc else None},
                run_id, tenant_id)
            return {"url": item.article_url, "title": item.title, "chunks": n, "source": page.source}

        seen_hosts: set[str] = set()
        picks = []
        for item in news:
            if not item.article_url:
                continue
            host = re.sub(r"^https?://([^/]+)/.*$", r"\1", item.article_url + "/")
            if host in seen_hosts:
                continue
            seen_hosts.add(host)
            picks.append(item)
            if len(picks) >= _NEWS_SCRAPE_TOP_N:
                break

        scraped = await asyncio.gather(*(scrape_and_store(i) for i in picks), return_exceptions=True)
        ingested = []
        for item, res in zip(picks, scraped):
            if isinstance(res, BaseException):
                errors.append(_err(f"news.scrape[{item.article_url}]", res))
            else:
                ingested.append(res)

        transcript: dict[str, Any] | None = None
        if state.get("quarter"):
            try:
                text = await scraper.scrape_earnings_transcript(ticker, str(state["quarter"]))
                n = await vs.ingest_text(text, {"ticker": ticker, "kind": "transcript",
                                                "quarter": state["quarter"]}, run_id, tenant_id)
                transcript = {"quarter": state["quarter"], "chunks": n, "chars": len(text)}
            except Exception as exc:  # noqa: BLE001
                errors.append(_err("news.transcript", exc))

        data = {
            "ticker": ticker,
            "items": [{"title": n.title, "publisher": n.publisher, "url": n.article_url,
                       "published_utc": n.published_utc.isoformat() if n.published_utc else None,
                       "sentiment": n.sentiment, "sentiment_reasoning": n.sentiment_reasoning,
                       "description": (n.description or "")[:300]} for n in news],
            "ingested_articles": ingested, "transcript": transcript,
            "retrieval": {"run_id": run_id, "tenant_id": tenant_id,
                          "metadata_filter": {"kind": "news"}},
            "status": _status(bool(news), errors),
        }
        await self._stash(run_id, "news_data", data)
        return self._merge(state, errors, news_data=data)

    # ------------------------------------------------------------------ quant executor
    async def inject_quant_data(self, state: AgentState) -> AgentState:
        """Fourth executor: computed metrics via the E2B sandbox. Uses state['market_data'] if present,
        otherwise fetches financials itself, so it is safe to run in parallel with the other injectors."""
        (run_id,) = _require(state, "run_id")
        md = state.get("market_data") or {}
        errors: list[dict[str, Any]] = []
        data: dict[str, Any] = {"status": "error", "metrics": None}
        try:
            price = (md.get("snapshot") or {}).get("price")
            if md.get("financials"):
                periods = [FinancialPeriod(**f) for f in md["financials"]]
            else:
                # market_data not in state yet (executors may run in parallel): fetch directly.
                # Both calls are Redis-cached, so this costs nothing extra when market_data also ran.
                (ticker,) = _require(state, "ticker")
                market = self.reg.get_market_tool()
                fin, snap = await asyncio.gather(market.get_financials(ticker, limit=8),
                                                 market.get_stock_snapshot(ticker), return_exceptions=True)
                if isinstance(fin, BaseException):
                    raise fin
                periods = fin
                price = None if isinstance(snap, BaseException) else snap.price
            if not periods:
                raise ToolError("no financial periods available for quant metrics")
            shares = next((p.diluted_shares for p in sorted(periods, key=lambda p: p.end_date or "", reverse=True)
                           if p.diluted_shares), None)
            market_cap = price * shares if price and shares else None
            metrics = await self.reg.get_sandbox_tool().compute_metrics(periods, price=price, market_cap=market_cap)
            data = {"status": "ok", "metrics": metrics.model_dump(), "price": price,
                    "market_cap_estimate": market_cap,
                    "market_cap_basis": "price x latest diluted weighted-average shares" if market_cap else None}
        except Exception as exc:  # noqa: BLE001
            errors.append(_err("quant.compute_metrics", exc))
        await self._stash(run_id, "quant_data", data)
        return self._merge(state, errors, quant_data=data)

    # ------------------------------------------------------------------ helpers
    async def _stash(self, run_id: str, key: str, value: Any) -> None:
        try:
            await self.reg.get_scratchpad(run_id).set(key, value)
        except Exception as exc:  # noqa: BLE001 - scratchpad is best-effort
            log_event(log, logging.WARNING, "scratchpad_stash_failed", key=key, error=repr(exc))

    @staticmethod
    def _merge(state: AgentState, new_errors: list[dict[str, Any]], **updates: Any) -> AgentState:
        out: dict[str, Any] = dict(updates)
        if new_errors:
            out["errors"] = new_errors  # `errors` has an operator.add reducer in AgentState
        return out  # type: ignore[return-value]  # partial update; LangGraph merges into state

    def _timed(self, name: str, fn: NodeFn) -> NodeFn:
        async def node(state: AgentState) -> AgentState:
            t0 = time.perf_counter()
            try:
                out = await fn(state)
            except Exception as exc:  # noqa: BLE001 - a Layer 3 failure must not crash the graph
                log_event(log, logging.ERROR, "injector_node_failed", node=name, error=repr(exc))
                return {"errors": [_err(name, exc)]}  # type: ignore[return-value]
            log_event(log, logging.INFO, "injector_node_done", node=name, run_id=state.get("run_id"),
                      ms=round((time.perf_counter() - t0) * 1000, 1))
            return out

        node.__name__ = name
        return node

    def nodes(self) -> dict[str, NodeFn]:
        """kind -> LangGraph node. Kinds: market_data, filings, news, quant."""
        return {
            "market_data": self._timed("layer3_inject_market_data", self.inject_market_data),
            "filings": self._timed("layer3_inject_filings", self.inject_filings_data),
            "news": self._timed("layer3_inject_news", self.inject_news_data),
            "quant": self._timed("layer3_inject_quant", self.inject_quant_data),
        }

    async def inject_all(self, state: AgentState) -> AgentState:
        """ONE node that fills market_data, filings_data, news_data and quant_data.

        Use this when Layer 2 has a single `parallel_executor` node (planner -> parallel_executor).
        market/filings/news run concurrently, then quant runs with their output. If the data is already in
        state (e.g. the verifier looped back to the planner) it does nothing, so filings are not re-ingested.
        """
        if all(state.get(k) for k in ("market_data", "filings_data", "news_data", "quant_data")):
            return {}  # type: ignore[return-value]
        nodes = self.nodes()
        first = await asyncio.gather(nodes["market_data"](state), nodes["filings"](state), nodes["news"](state))
        merged: dict[str, Any] = {}
        errors: list[dict[str, Any]] = []
        for upd in first:
            errors.extend(upd.get("errors", []))
            merged.update({k: v for k, v in upd.items() if k != "errors"})
        quant = await nodes["quant"]({**state, **merged})  # type: ignore[arg-type]
        errors.extend(quant.get("errors", []))
        merged.update({k: v for k, v in quant.items() if k != "errors"})
        if errors:
            merged["errors"] = errors
        return merged  # type: ignore[return-value]

    def wire_before(self, builder: Any, target: str, node_name: str = "layer3_inject_all") -> None:
        """Insert the single inject_all node immediately BEFORE `target` (e.g. "parallel_executor").
        Call on the un-compiled StateGraph. Static edges into `target` are re-pointed at the injector.
        Conditional edges that route to `target` are reported, not rewired (use `node_name` in their path_map)."""
        builder.add_node(node_name, self._timed(node_name, self.inject_all))
        for src, dst in [e for e in list(builder.edges) if e[1] == target]:
            builder.edges.discard((src, dst))
            builder.add_edge(src, node_name)
        waiting = getattr(builder, "waiting_edges", None)
        if waiting:
            for starts, end in [w for w in list(waiting) if w[1] == target]:
                waiting.discard((starts, end))
                builder.add_edge(list(starts), node_name)
        builder.add_edge(node_name, target)
        for src, branches in getattr(builder, "branches", {}).items():
            for bname, branch in branches.items():
                ends = getattr(branch, "ends", None) or {}
                if target in (ends.values() if isinstance(ends, dict) else ends):
                    log_event(log, logging.WARNING, "conditional_edge_not_rewired",
                              source=src, branch=bname, executor=target, inject_node=node_name)

    def wire_into_graph(self, builder: Any, executors: dict[str, str]) -> None:
        """Insert an injector node immediately BEFORE each executor.

        `builder` is a langgraph StateGraph (not yet compiled).
        `executors` maps injector kind -> existing executor node name, e.g.
            {"market_data": "market_executor", "filings": "filings_executor",
             "news": "news_executor", "quant": "quant_executor"}
        Static edges (incl. START edges and join edges) into the executor are re-pointed at the injector.
        Conditional edges / Send fan-outs that target an executor are reported, not rewired: point their
        path_map at the `layer3_inject_*` node name instead.
        """
        nodes = self.nodes()
        for kind, executor in executors.items():
            if kind not in nodes:
                raise ValueError(f"unknown injector kind {kind!r}; expected one of {list(nodes)}")
            inj_name = f"layer3_inject_{kind}"
            builder.add_node(inj_name, nodes[kind])

            for src, dst in [e for e in list(builder.edges) if e[1] == executor]:
                builder.edges.discard((src, dst))
                builder.add_edge(src, inj_name)
            waiting = getattr(builder, "waiting_edges", None)
            if waiting:
                for starts, end in [w for w in list(waiting) if w[1] == executor]:
                    waiting.discard((starts, end))
                    builder.add_edge(list(starts), inj_name)
            builder.add_edge(inj_name, executor)

            for src, branches in getattr(builder, "branches", {}).items():
                for bname, branch in branches.items():
                    ends = getattr(branch, "ends", None) or {}
                    if executor in (ends.values() if isinstance(ends, dict) else ends):
                        log_event(log, logging.WARNING, "conditional_edge_not_rewired",
                                  source=src, branch=bname, executor=executor, inject_node=inj_name)


# --------------------------------------------------------------------------- smoke test
async def _demo() -> None:
    import json
    import os

    from .config import ConfigError

    try:
        await ToolRegistry.initialize()
    except ConfigError as exc:
        print(f"config incomplete — skipping live test: {exc}")
        return
    try:
        inj = ToolInjector()
        state: AgentState = {"run_id": "demo-run", "tenant_id": "demo-tenant", "ticker": "AAPL",
                             "quarter": os.environ.get("DEMO_QUARTER", "")}
        for fn in (inj.inject_market_data, inj.inject_quant_data, inj.inject_filings_data, inj.inject_news_data):
            update = await fn(state)
            errs = [*state.get("errors", []), *update.pop("errors", [])]  # mimic the operator.add reducer
            state = {**state, **update, "errors": errs}  # type: ignore[typeddict-item]
        brief = {k: (v.get("status") if isinstance(v, dict) else len(v))
                 for k, v in state.items() if k in ("market_data", "filings_data", "news_data", "quant_data", "errors")}
        print(json.dumps(brief, indent=2))
        for e in state.get("errors", []):
            print("error:", e)
    finally:
        await ToolRegistry.shutdown()


if __name__ == "__main__":
    asyncio.run(_demo())
