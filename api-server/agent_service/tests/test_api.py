from __future__ import annotations

import json
import threading
import time
import uuid

import jwt
import psycopg
from conftest import _OTHER, auth, make_token

SUBMIT = {"ticker": "aapl", "quarter": "2025Q3", "query": "How did margins trend?", "workflow_type": "earnings_analysis"}


def _db(infra):
    return psycopg.connect(infra.dsn, autocommit=True)


# ------------------------------------------------------------------ auth
def test_auth_rejections(client):
    assert client.get("/research/history").status_code == 401                                   # no header
    assert client.get("/research/history", headers={"Authorization": "Bearer garbage"}).status_code == 401
    expired = client.get("/research/history", headers=auth(exp_delta=-3600))
    assert expired.status_code == 401 and expired.json()["detail"] == "Token expired"
    forged = client.get("/research/history", headers={"Authorization": f"Bearer {make_token(key=_OTHER)}"})
    assert forged.status_code == 401
    wrong_iss = client.get("/research/history", headers=auth(issuer="https://evil.test"))
    assert wrong_iss.status_code == 401
    no_org = client.get("/research/history", headers=auth(org_id=None))
    assert no_org.status_code == 401 and "organization" in no_org.json()["detail"]
    assert client.get("/research/history", headers=auth()).status_code == 200
    assert client.get("/health").status_code == 200                                              # public


def test_jwks_unreachable_is_503(client, monkeypatch):
    import middleware.auth as auth_mod

    def boom(_tok):
        raise jwt.PyJWKClientConnectionError("dns failure")

    monkeypatch.setattr(auth_mod, "_jwks", lambda: type("J", (), {"get_signing_key_from_jwt": staticmethod(boom)})())
    r = client.get("/research/history", headers=auth())
    assert r.status_code == 503 and "JWKS" in r.json()["detail"]


def test_request_id_header(client):
    r = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"
    assert client.get("/health").headers["x-request-id"]


# ---------------------------------------------------------------- submit
def test_submit_passes_ticker_and_quarter_to_temporal(client, fake_temporal, infra):
    r = client.post("/research/submit", json=SUBMIT, headers=auth())
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued" and body["estimated_duration_seconds"] == 420
    call = fake_temporal.started[-1]
    assert call["name"] == "MarketResearchWorkflow"
    assert call["task_queue"] == "market-research"
    assert call["id"] == f"research-{body['run_id']}"
    arg = call["arg"]
    assert arg["ticker"] == "AAPL" and arg["quarter"] == "2025Q3"                      # upper-cased, passed through
    assert arg["agent_state"] == {"ticker": "AAPL", "quarter": "2025Q3", "errors": [], "run_id": body["run_id"]}
    assert arg["tenant_id"] and arg["run_id"] == body["run_id"]
    with _db(infra) as c:
        row = c.execute("select ticker, quarter, status, tenant_id from workflow_runs where id=%s", (body["run_id"],)).fetchone()
    assert row[0] == "AAPL" and row[1] == "2025Q3" and row[2] == "queued"


def test_submit_validation(client):
    h = auth()
    assert client.post("/research/submit", json={"ticker": "AA PL", "query": "valid query"}, headers=h).status_code == 422
    assert client.post("/research/submit", json={"ticker": "AAPL", "query": "x"}, headers=h).status_code == 422
    assert client.post("/research/submit", json={"ticker": "AAPL", "query": "valid", "workflow_type": "nope"}, headers=h).status_code == 422
    assert client.post("/research/submit", json={"ticker": "AAPL", "query": "valid", "quarter": "x;drop table"}, headers=h).status_code == 422
    assert client.post("/research/submit", json={"ticker": "A" * 11, "query": "valid"}, headers=h).status_code == 422
    assert client.post("/research/submit", content=b"not json", headers={**h, "Content-Type": "application/json"}).status_code == 422


def test_submit_without_quarter_passes_null(client, fake_temporal):
    r = client.post("/research/submit", json={"ticker": "msft", "query": "no quarter given"}, headers=auth())
    assert r.status_code == 202
    assert fake_temporal.started[-1]["arg"]["quarter"] is None


def test_submit_temporal_down_503_and_no_ghost_row(client, fake_temporal, infra, monkeypatch):
    from services import temporal_service

    client.app.state.temporal = None

    async def dead():
        raise ConnectionRefusedError("nope")

    monkeypatch.setattr(temporal_service, "connect", dead)
    with _db(infra) as c:
        before = c.execute("select count(*) from workflow_runs").fetchone()[0]
    r = client.post("/research/submit", json=SUBMIT, headers=auth())
    assert r.status_code == 503 and "Temporal" in r.json()["detail"]
    with _db(infra) as c:
        assert c.execute("select count(*) from workflow_runs").fetchone()[0] == before


def test_submit_start_failure_marks_run_failed(client, fake_temporal, infra):
    fake_temporal.fail = True
    r = client.post("/research/submit", json={**SUBMIT, "ticker": "FAIL"}, headers=auth())
    assert r.status_code == 503
    with _db(infra) as c:
        row = c.execute("select status, trace_log_jsonb from workflow_runs where ticker='FAIL'").fetchone()
    assert row[0] == "failed" and "start failed" in json.dumps(row[1])


# ------------------------------------------------- status, tenant isolation
def test_status_and_tenant_isolation(client):
    run_id = client.post("/research/submit", json={**SUBMIT, "ticker": "ISO"}, headers=auth("org_A")).json()["run_id"]
    st = client.get(f"/research/{run_id}/status", headers=auth("org_A"))
    assert st.status_code == 200
    j = st.json()
    assert j["status"] == "queued" and j["ticker"] == "ISO" and j["progress_pct"] == 0 and j["duration_so_far"] >= 0
    assert client.get(f"/research/{run_id}/status", headers=auth("org_B")).status_code == 404   # other tenant
    assert client.get(f"/research/{run_id}/report", headers=auth("org_B")).status_code == 404
    assert client.get(f"/research/{run_id}/stream", headers=auth("org_B")).status_code == 404
    assert client.get(f"/research/{uuid.uuid4()}/status", headers=auth()).status_code == 404
    assert client.get("/research/not-a-uuid/status", headers=auth()).status_code == 422
    hist_b = client.get("/research/history?ticker=ISO", headers=auth("org_B")).json()
    assert hist_b["total"] == 0
    assert client.get("/research/history?ticker=ISO", headers=auth("org_A")).json()["total"] == 1


def test_history_filters_and_pagination(client):
    for t in ("HA", "HB", "HA"):
        client.post("/research/submit", json={**SUBMIT, "ticker": t}, headers=auth("org_H"))
    h = auth("org_H")
    assert client.get("/research/history", headers=h).json()["total"] == 3
    r = client.get("/research/history?ticker=ha", headers=h).json()
    assert r["total"] == 2 and all(i["ticker"] == "HA" for i in r["items"])
    p = client.get("/research/history?page=2&page_size=2", headers=h).json()
    assert len(p["items"]) == 1 and p["total_pages"] == 2
    assert client.get("/research/history?status=queued&workflow_type=earnings_analysis", headers=h).json()["total"] == 3
    assert client.get("/research/history?status=completed", headers=h).json()["total"] == 0
    assert client.get("/research/history?date_from=2999-01-01T00:00:00Z", headers=h).json()["total"] == 0
    assert client.get("/research/history?date_from=2999-01-01T00:00:00Z&date_to=2000-01-01T00:00:00Z", headers=h).status_code == 422
    assert client.get("/research/history?page_size=1000", headers=h).status_code == 422
    assert client.get("/research/history?status=bogus", headers=h).status_code == 422


# --------------------------------------------------- Redis -> Neon event sink
def test_event_sink_updates_status_from_redis_events(client):
    from integration.progress_events import publish_event_sync, register_steps

    register_steps(["market_data", "filings", "news", "quant"])
    run_id = client.post("/research/submit", json={**SUBMIT, "ticker": "SINK"}, headers=auth("org_S")).json()["run_id"]
    time.sleep(0.5)  # let the sink's psubscribe settle
    publish_event_sync(run_id, "step_started", {"step": "filings"})
    publish_event_sync(run_id, "step_completed", {"step": "filings", "progress_pct": 50})
    deadline = time.time() + 5
    j = {}
    while time.time() < deadline:
        j = client.get(f"/research/{run_id}/status", headers=auth("org_S")).json()
        if j["progress_pct"] == 50:
            break
        time.sleep(0.2)
    assert j["status"] == "running" and j["current_step"] == "filings" and j["progress_pct"] == 50


# ------------------------------------------------------------------- report
def test_report_lifecycle_with_run_store_and_odd_shapes(client, infra, monkeypatch):
    from integration import run_store

    monkeypatch.setenv("NEON_DATABASE_URL", infra.dsn)
    run_id = client.post("/research/submit", json={**SUBMIT, "ticker": "RPT"}, headers=auth("org_R")).json()["run_id"]
    h = auth("org_R")
    assert client.get(f"/research/{run_id}/report", headers=h).status_code == 409           # not ready

    run_store.update_step(run_id, "market_data", 25, {"node": "market_data"})
    assert client.get(f"/research/{run_id}/status", headers=h).json()["current_step"] == "market_data"
    run_store.save_citation(run_id, source_url="https://sec.gov/x", source_type="10-Q", metric_name="Revenue",
                            value=94.9, period="2025Q3", confidence=0.93, raw_snippet="Net sales were $94.9B")
    # Layer-3-shaped report: raw AgentState keys, no 'summary'/'sections'
    state_dump = {"ticker": "RPT", "quarter": "2025Q3", "market_data": {"close": 1.5}, "filings_data": [{"form": "10-Q"}],
                  "news_data": [], "quant_data": {"rsi": 51}, "errors": ["news: rate limited"]}
    run_store.save_report(run_id, state_dump)

    r = client.get(f"/research/{run_id}/report", headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["quarter"] == "2025Q3" and j["report"]["market_data"] == {"close": 1.5}        # nothing dropped
    assert j["report"]["errors"] == ["news: rate limited"]
    assert j["citations"][0]["metric_name"] == "Revenue" and j["citations"][0]["confidence"] == 0.93
    st = client.get(f"/research/{run_id}/status", headers=h).json()
    assert st["status"] == "completed" and st["progress_pct"] == 100


def test_report_pdf_real_pandoc_and_latex_injection(client, infra, monkeypatch):
    from integration import run_store

    monkeypatch.setenv("NEON_DATABASE_URL", infra.dsn)
    run_id = client.post("/research/submit", json={**SUBMIT, "ticker": "PDF"}, headers=auth("org_P")).json()["run_id"]
    evil = "Normal text. \\input{/etc/passwd} \\write18{touch /tmp/pwned_by_latex} $$x$$"
    run_store.save_report(run_id, {"summary": evil, "sections": [{"title": "S1", "content": "body <b>x</b>"}],
                                   "conflicts": ["a | b conflict"]})
    r = client.get(f"/research/{run_id}/report?format=pdf", headers=auth("org_P"))
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"] == "application/pdf" and r.content[:4] == b"%PDF"
    import os
    assert not os.path.exists("/tmp/pwned_by_latex")
    assert client.get(f"/research/{run_id}/report?format=docx", headers=auth("org_P")).status_code == 422


def test_pdf_unavailable_is_501(client, infra, monkeypatch):
    from integration import run_store
    from services import report_service

    monkeypatch.setenv("NEON_DATABASE_URL", infra.dsn)
    run_id = client.post("/research/submit", json={**SUBMIT, "ticker": "NOPD"}, headers=auth("org_N")).json()["run_id"]
    run_store.save_report(run_id, {"summary": "x"})
    monkeypatch.setattr(report_service.shutil, "which", lambda _n: None)
    r = client.get(f"/research/{run_id}/report?format=pdf", headers=auth("org_N"))
    assert r.status_code == 501 and "Pandoc" in r.json()["detail"]


# --------------------------------------------------------------------- SSE
def _collect_sse(client, run_id, headers, out):
    with client.stream("GET", f"/research/{run_id}/stream", headers=headers) as resp:
        out["status"] = resp.status_code
        out["ctype"] = resp.headers["content-type"]
        ev = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                ev = line.split(":", 1)[1].strip()
                out.setdefault("events", []).append(ev)
            elif line.startswith("data:") and ev:
                out.setdefault("data", {})[ev] = json.loads(line.split(":", 1)[1])


def test_sse_streams_events_and_closes_on_report_ready(client):
    from integration.progress_events import publish_event_sync

    run_id = client.post("/research/submit", json={**SUBMIT, "ticker": "SSE"}, headers=auth("org_E")).json()["run_id"]
    out: dict = {}
    t = threading.Thread(target=_collect_sse, args=(client, run_id, auth("org_E"), out))
    t.start()
    deadline = time.time() + 5
    while "events" not in out and time.time() < deadline:
        time.sleep(0.05)
    time.sleep(0.6)  # subscription established after 'connected'
    publish_event_sync(run_id, "step_started", {"step": "market_data"})
    publish_event_sync(run_id, "conflict_found", {"step": "analyze", "conflict": {"description": "EPS mismatch"}})
    publish_event_sync(run_id, "step_completed", {"step": "market_data", "progress_pct": 40})
    publish_event_sync(run_id, "report_ready", {"run_id": run_id})
    t.join(timeout=15)
    assert not t.is_alive(), "stream did not close on report_ready"
    assert out["status"] == 200 and out["ctype"].startswith("text/event-stream")
    assert out["events"] == ["connected", "step_started", "conflict_found", "step_completed", "report_ready"]
    assert out["data"]["conflict_found"]["payload"]["conflict"]["description"] == "EPS mismatch"


def test_sse_closes_when_run_fails(client, infra, monkeypatch):
    from integration import run_store

    monkeypatch.setenv("NEON_DATABASE_URL", infra.dsn)
    run_id = client.post("/research/submit", json={**SUBMIT, "ticker": "SSF"}, headers=auth("org_E")).json()["run_id"]
    out: dict = {}
    t = threading.Thread(target=_collect_sse, args=(client, run_id, auth("org_E"), out))
    t.start()
    time.sleep(1.0)
    run_store.mark_failed(run_id, "polygon: 429 plan limit")
    t.join(timeout=15)
    assert not t.is_alive()
    assert out["events"][-1] == "run_ended" and out["data"]["run_ended"]["payload"]["status"] == "failed"


def test_sse_for_already_completed_run_and_timeout(client, infra, monkeypatch):
    from config import get_settings
    from integration import run_store

    monkeypatch.setenv("NEON_DATABASE_URL", infra.dsn)
    run_id = client.post("/research/submit", json={**SUBMIT, "ticker": "SSD"}, headers=auth("org_E")).json()["run_id"]
    run_store.save_report(run_id, {"summary": "done"})
    out: dict = {}
    _collect_sse(client, run_id, auth("org_E"), out)
    assert out["events"] == ["connected", "report_ready"]

    run2 = client.post("/research/submit", json={**SUBMIT, "ticker": "SST"}, headers=auth("org_E")).json()["run_id"]
    monkeypatch.setattr(get_settings(), "sse_timeout_seconds", 2)
    out2: dict = {}
    t0 = time.time()
    _collect_sse(client, run2, auth("org_E"), out2)
    assert out2["events"][-1] == "timeout" and 1.5 < time.time() - t0 < 6


# --------------------------------------------------------------- workflows
def test_templates(client):
    r = client.get("/workflows/templates", headers=auth())
    assert r.status_code == 200 and len(r.json()) == 5
    assert client.get("/workflows/templates").status_code == 401


def test_schedule_crud_and_run_due(client, fake_temporal, infra):
    admin, member = auth("org_W", "org:admin"), auth("org_W", "org:member")
    body = {"ticker": "nvda", "workflow_type": "earnings_analysis", "cron_expr": "* * * * *"}
    assert client.post("/workflows/schedule", json=body, headers=member).status_code == 403
    assert client.post("/workflows/schedule", json={**body, "cron_expr": "not a cron"}, headers=admin).status_code == 422
    assert client.post("/workflows/schedule", json={**body, "cron_expr": "* * * *"}, headers=admin).status_code == 422
    r = client.post("/workflows/schedule", json=body, headers=admin)
    assert r.status_code == 201, r.text
    sched = r.json()
    assert sched["ticker"] == "NVDA" and sched["active"] and "INNGEST_EVENT_KEY" in sched["warning"]   # graceful, no key
    assert len(client.get("/workflows/schedules", headers=member).json()["items"]) == 1
    assert client.get("/workflows/schedules", headers=auth("org_W2")).json()["items"] == []            # tenant isolated

    # internal runner: key checks
    assert client.post("/internal/schedules/run-due").status_code == 401
    assert client.post("/internal/schedules/run-due", headers={"X-Internal-Key": "wrong"}).status_code == 401
    with psycopg.connect(infra.dsn, autocommit=True) as c:
        c.execute("update workflow_schedules set created_at = now() - interval '5 minutes' where id=%s", (sched["id"],))
    n = len(fake_temporal.started)
    fired = client.post("/internal/schedules/run-due", headers={"X-Internal-Key": "test-internal-key"}).json()
    assert fired["fired"] == [sched["id"]] and fired["errors"] == []
    assert len(fake_temporal.started) == n + 1 and fake_temporal.started[-1]["arg"]["ticker"] == "NVDA"
    again = client.post("/internal/schedules/run-due", headers={"X-Internal-Key": "test-internal-key"}).json()
    assert again["fired"] == []                                                                         # not due again yet

    assert client.delete(f"/workflows/schedule/{sched['id']}", headers=member).status_code == 403
    assert client.delete(f"/workflows/schedule/{sched['id']}", headers=auth("org_W2")).status_code == 404
    assert client.delete(f"/workflows/schedule/{sched['id']}", headers=admin).status_code == 204
    assert client.delete(f"/workflows/schedule/{sched['id']}", headers=admin).status_code == 404
    assert client.get("/workflows/schedules", headers=admin).json()["items"] == []


def test_inngest_failure_is_nonfatal(client, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "inngest_event_key", "k")
    monkeypatch.setattr(get_settings(), "inngest_event_url", "http://127.0.0.1:9")   # closed port
    r = client.post("/workflows/schedule", headers=auth("org_I"),
                    json={"ticker": "IBM", "workflow_type": "full_research", "cron_expr": "0 9 * * 1-5"})
    assert r.status_code == 201 and "not notified" in r.json()["warning"]


# ------------------------------------------------------------ misc/errors
def test_db_outage_returns_503(client, monkeypatch):
    from db import queries
    from psycopg import OperationalError

    async def boom(*a, **k):
        raise OperationalError("connection refused")

    monkeypatch.setattr(queries, "list_runs_by_tenant", boom)
    r = client.get("/research/history", headers=auth())
    assert r.status_code == 503 and "Neon" in r.json()["detail"]


def test_health_reports_components(client):
    j = client.get("/health").json()
    assert j == {"status": "ok", "neon": True, "redis": True, "temporal": True}


def test_internal_disabled_without_key(client, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "internal_api_key", "")
    assert client.post("/internal/schedules/run-due", headers={"X-Internal-Key": "x"}).status_code == 503


def test_access_log_has_required_fields(fake_temporal, monkeypatch, capsys):
    import middleware.auth as auth_mod
    from conftest import _KEY
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from main import create_app

    monkeypatch.setattr(auth_mod, "_jwks", lambda: SimpleNamespace(
        get_signing_key_from_jwt=lambda tok: SimpleNamespace(key=_KEY.public_key())))
    with TestClient(create_app()) as c:
        run_id = c.post("/research/submit", json={**SUBMIT, "ticker": "LOG"}, headers=auth("org_L")).json()["run_id"]
        c.get(f"/research/{run_id}/status", headers=auth("org_L"))
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.startswith("{")]
    access = [l for l in lines if l.get("message") == "request" and l.get("path", "").endswith("/status")]
    assert access, lines[-5:]
    rec = access[0]
    assert rec["run_id"] == run_id and rec["tenant_id"] not in ("-", None) and rec["duration_ms"] >= 0
    assert rec["status"] == 200 and rec["request_id"] and rec["method"] == "GET"
