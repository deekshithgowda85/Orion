"""Layer 2/3 integration: real LangGraph graph whose state uses Layer 3's keys, real Redis."""
from __future__ import annotations

import asyncio
import json
import operator
import os
import subprocess
import sys
import time
from typing import Annotated, TypedDict

import pytest
import redis as redis_sync
from langgraph.graph import END, START, StateGraph

from integration import progress_events as pe


class AgentState(TypedDict, total=False):
    """Exactly the keys named for Layer 3. NOTE: no run_id here on purpose."""
    ticker: str
    quarter: str
    market_data: dict
    filings_data: list
    news_data: list
    quant_data: dict
    errors: Annotated[list, operator.add]


class AgentStateWithRun(AgentState, total=False):
    run_id: str


def _listen(run_id: str):
    r = redis_sync.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    ps = r.pubsub()
    ps.subscribe(pe.channel_for(run_id))
    ps.get_message(timeout=1)  # subscribe ack
    ps._test_keepalive = r      # Redis.__del__ would close the pool (and this subscription) if `r` were collected
    return ps


def _drain(ps, expect_min: int = 0, wait: float = 2.0) -> list[dict]:
    out, end = [], time.time() + wait
    while time.time() < end:
        m = ps.get_message(ignore_subscribe_messages=True, timeout=0.2)
        if m:
            out.append(json.loads(m["data"]))
        elif len(out) >= expect_min and expect_min:
            break
    return out


def _build(state_cls):
    @pe.with_progress_events("fetch_market")
    def market_data(state: dict) -> dict:
        return {"market_data": {"ticker": state["ticker"], "px": 1.0}}

    @pe.with_progress_events("fetch_filings")
    async def filings(state: dict) -> dict:
        return {"filings_data": [{"form": "10-Q", "quarter": state["quarter"]}], "conflicts": [{"description": "rev mismatch"}]}

    @pe.with_progress_events("run_quant")
    def quant(state: dict, config) -> dict:      # node that takes `config` - signature must survive the decorator
        return {"quant_data": {"rsi": 50, "cfg_run": (config.get("configurable") or {}).get("run_id")}}

    g = StateGraph(state_cls)
    g.add_node("fetch_market", market_data)
    g.add_node("fetch_filings", filings)
    g.add_node("run_quant", quant)
    g.add_edge(START, "fetch_market")
    g.add_edge("fetch_market", "fetch_filings")
    g.add_edge("fetch_filings", "run_quant")
    g.add_edge("run_quant", END)
    return g.compile()


@pytest.fixture(autouse=True)
def _reset_client():
    pe._client = None
    pe._STEP_PROGRESS.clear()
    yield
    pe._client = None


def test_layer3_state_without_run_id_does_not_crash_and_emits_nothing():
    graph = _build(AgentState)
    ps = _listen("none")
    out = asyncio.run(graph.ainvoke({"ticker": "AAPL", "quarter": "2025Q3", "errors": []}))
    assert out["ticker"] == "AAPL" and out["quarter"] == "2025Q3" and out["market_data"]["px"] == 1.0
    assert out["filings_data"][0]["quarter"] == "2025Q3" and out["errors"] == []
    assert _drain(ps, wait=0.6) == []


def test_run_id_via_langgraph_config_emits_events_in_order():
    pe.register_steps(["fetch_market", "fetch_filings", "run_quant"])
    graph = _build(AgentState)
    rid = "run-config-1"
    ps = _listen(rid)
    out = asyncio.run(graph.ainvoke({"ticker": "AAPL", "quarter": "2025Q3", "errors": []}, {"configurable": {"run_id": rid}}))
    assert out["quant_data"]["cfg_run"] == rid
    evs = _drain(ps, expect_min=7)
    seq = [(e["type"], e["payload"].get("step")) for e in evs]
    assert seq == [
        ("step_started", "fetch_market"), ("step_completed", "fetch_market"),
        ("step_started", "fetch_filings"), ("conflict_found", "fetch_filings"), ("step_completed", "fetch_filings"),
        ("step_started", "run_quant"), ("step_completed", "run_quant"),
    ], seq
    assert evs[1]["payload"]["progress_pct"] == 32 and evs[-1]["payload"]["progress_pct"] == 95


def test_run_id_in_state_when_declared_on_agentstate():
    graph = _build(AgentStateWithRun)
    rid = "run-state-1"
    ps = _listen(rid)
    asyncio.run(graph.ainvoke({"ticker": "MSFT", "quarter": "2025Q2", "run_id": rid, "errors": []}))
    types = [e["type"] for e in _drain(ps, expect_min=7)]
    assert types.count("step_started") == 3 and types.count("step_completed") == 3 and "conflict_found" in types


def test_run_id_not_declared_in_state_is_dropped_by_langgraph():
    """Documents why AgentState MUST declare run_id (or use configurable): undeclared keys never reach nodes."""
    graph = _build(AgentState)
    rid = "run-dropped"
    ps = _listen(rid)
    asyncio.run(graph.ainvoke({"ticker": "X", "quarter": "Q1", "run_id": rid, "errors": []}))
    assert _drain(ps, wait=0.6) == []


def test_redis_down_never_breaks_a_node(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    pe._client = None
    graph = _build(AgentState)
    t0 = time.time()
    out = asyncio.run(graph.ainvoke({"ticker": "AAPL", "quarter": "2025Q3", "errors": []}, {"configurable": {"run_id": "r"}}))
    assert out["quant_data"]["rsi"] == 50
    assert time.time() - t0 < 15


def test_publish_report_ready():
    ps = _listen("rr")
    assert pe.publish_report_ready("rr", "done") is True
    assert _drain(ps, expect_min=1)[0]["type"] == "report_ready"


def test_missing_config_gives_one_clear_message(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("NEON_DATABASE_URL", "CLERK_JWKS_URL")}
    p = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0, %r); import main" % os.getcwd()],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert p.returncode != 0
    assert "NEON_DATABASE_URL" in p.stderr and "CLERK_JWKS_URL" in p.stderr and "Traceback" not in p.stderr, p.stderr


def test_no_layer3_name_dependencies():
    """Layer 4 must not import Layer 3 symbols."""
    import pathlib, re
    hits = []
    for f in pathlib.Path(".").rglob("*.py"):
        if "tests" in f.parts:
            continue
        txt = f.read_text()
        for name in ("ToolRegistry", "ToolInjector"):
            if re.search(rf"\b{name}\b", txt):
                hits.append((str(f), name))
    assert hits == []


def test_start_workflow_kwargs_exist_in_installed_temporalio_sdk():
    """No Temporal server here, so verify every kwarg we pass against the real SDK signature."""
    import inspect
    from temporalio.client import Client

    params = set(inspect.signature(Client.start_workflow).parameters)
    for kw in ("id", "task_queue", "execution_timeout", "id_reuse_policy", "rpc_timeout"):
        assert kw in params, f"temporalio.Client.start_workflow has no '{kw}' parameter"
    assert hasattr(Client, "connect")
