# Market Research Agent — Layer 4 (API layer)

```
market-research-api/
├── README.md                      this file
├── LAYER4_INTEGRATION.md          edits needed in Layers 1-3
├── docker-compose.api.yml         merge into your existing compose file
├── .gitignore                     ignores .env, .venv, node_modules, dist, __pycache__
├── agent_service/                 FastAPI, Python 3.11+, port 8000
│   ├── main.py                    app factory, lifespan (Redis, Neon pool, Temporal, event sink), CORS, /health, error handlers
│   ├── config.py                  all settings from env/.env; one clear message if required vars are missing
│   ├── logging_config.py          JSON logs (run_id, tenant_id, request_id, duration_ms)
│   ├── requirements.txt / requirements-dev.txt / pytest.ini / Dockerfile / .dockerignore / .env.example
│   ├── middleware/
│   │   ├── auth.py                verifies the Clerk JWT (RS256 via JWKS), maps Clerk org -> tenant, sets request.state.user
│   │   └── request_context.py     X-Request-ID on every response + one JSON access-log line per request
│   ├── models/
│   │   ├── research.py            Pydantic v2 models for submit/status/report/history
│   │   └── workflows.py           Pydantic v2 models for templates/schedules (validates cron)
│   ├── routes/
│   │   ├── research.py            submit, status, SSE stream, report (JSON/PDF), history
│   │   ├── workflows.py           templates, create/list/delete schedules
│   │   └── internal.py            POST /internal/schedules/run-due (shared-secret protected)
│   ├── services/
│   │   ├── temporal_service.py    connects to Temporal (lazy reconnect) and starts the workflow; build_workflow_input() = Layer 1 contract
│   │   ├── run_submit.py          shared "create run row + start workflow" used by submit and the scheduler
│   │   ├── event_sink.py          background task copying Redis progress events into Neon (current_step, progress_pct)
│   │   ├── report_service.py      report -> Markdown -> PDF with Pandoc; clear 501 if Pandoc/LaTeX missing; LaTeX injection disabled
│   │   └── inngest_service.py     optional Inngest Event API notifications
│   ├── db/
│   │   ├── schema.sql             tenants, workflow_runs, citations, workflow_schedules + indexes
│   │   └── queries.py             async psycopg pool and all queries (tenant-scoped)
│   ├── integration/               FILES YOU COPY INTO OTHER LAYERS (no dependency on the rest of agent_service)
│   │   ├── progress_events.py     Layer 2: @with_progress_events decorator + publish_report_ready
│   │   └── run_store.py           Layer 1: sync writers (update_step, save_report, save_citation, mark_failed)
│   └── tests/                     33 tests (real Postgres + Redis + LangGraph; Temporal faked)
└── bff_gateway/                   Node 20 + Express + TypeScript strict, port 3001
    ├── package.json / tsconfig.json / Dockerfile / .dockerignore / .env.example
    ├── src/
    │   ├── server.ts              starts the server, graceful shutdown, no request timeout for SSE
    │   ├── app.ts                 Helmet, CORS, request-id log, auth stack, rate limits, proxy; createApp({authStack}) for tests
    │   ├── config.ts              Zod-validated env; readable message when something is missing
    │   ├── lib/redis.ts, db.ts    ioredis client (with call timeout helper) and pg pool + tenant upsert
    │   ├── middleware/auth.ts     401 JSON instead of Clerk's redirect
    │   ├── middleware/tenant.ts   Clerk org -> tenant (Redis cache 300s), sets X-Tenant-ID / X-User-ID (overwrites client values)
    │   ├── middleware/rateLimit.ts  100 req/min per user, 20 submits/hour per tenant (Redis store, fails open)
    │   ├── middleware/validate.ts Zod validation -> structured 422
    │   ├── schemas/               ResearchSubmitSchema, WorkflowScheduleSchema
    │   └── routes/                proxy.ts (/api/research, /api/workflows -> FastAPI), user.ts, health.ts
    └── test/                      16 tests (real Express/proxy/Redis/Postgres; Clerk and FastAPI faked)
```

## Request flow

1. Browser sends `POST /api/research/submit` with the Clerk session token to the **BFF (3001)**.
2. BFF: Helmet/CORS → request-id → Clerk verifies the token → tenant middleware maps Clerk `org_id` to a tenant UUID (Redis cache, Neon fallback) and sets `X-Tenant-ID`/`X-User-ID` → per-user rate limit → submit rate limit → Zod validation (422 on error) → proxy to **FastAPI (8000)** `/research/submit`.
3. FastAPI re-verifies the JWT itself (it never trusts the headers), resolves the tenant, validates with Pydantic, checks Temporal is reachable, inserts a `workflow_runs` row (`queued`), starts the Temporal workflow `research-<run_id>` with ticker/quarter/query, and returns `202 {run_id, status:"queued", estimated_duration_seconds}`.
4. **Layer 1** worker runs the workflow → **Layer 2/3** LangGraph nodes run. Each decorated node publishes `step_started`/`step_completed`/`conflict_found` to Redis `run:<run_id>:events`.
5. FastAPI's event sink copies those into Neon (`current_step`, `progress_pct`); `GET /research/<id>/status` reads Neon.
6. `GET /research/<id>/stream` (SSE) subscribes to the same Redis channel and forwards events live (and every ~5 s checks Neon so a failed/finished run always closes the stream; 35-minute cap).
7. Layer 1 saves the report (`run_store.save_report`) and publishes `report_ready`; `GET /research/<id>/report` returns it (`?format=pdf` → Pandoc).

## Run on Windows (PowerShell)

Prerequisites: Python 3.11+, Node 20+, a Redis (WSL/Docker/Memurai), your Temporal server, a Neon project, a Clerk app **with Organizations enabled**. For PDFs: Pandoc + MiKTeX (or any LaTeX).

```powershell
# one-time: create tables in Neon (psql from https://www.postgresql.org/download/windows/, or paste schema.sql into Neon's SQL editor)
psql "$env:NEON_DATABASE_URL" -f agent_service\db\schema.sql

# --- agent service (terminal 1) ---
cd agent_service
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
Copy-Item .env.example .env           # then edit .env
uvicorn main:app --host 0.0.0.0 --port 8000      # must be run from inside agent_service

# --- BFF (terminal 2) ---
cd bff_gateway
npm install
Copy-Item .env.example .env           # then edit .env
npm run dev                           # or: npm run build; npm start
```

## Environment variables

**agent_service/.env**

| Variable | Required | Where to get it |
|---|---|---|
| `NEON_DATABASE_URL` | **yes** | Neon console → project → Connection Details |
| `CLERK_JWKS_URL` | **yes** | Clerk dashboard → API Keys → Show JWT public key → JWKS URL (`https://<instance>/.well-known/jwks.json`) |
| `CLERK_ISSUER` | recommended | Clerk "Frontend API URL" (`https://<instance>.clerk.accounts.dev`); enforces the token issuer |
| `TEMPORAL_HOST` | yes in practice (default `localhost:7233`) | where your Layer 1 Temporal server listens |
| `REDIS_URL` | yes in practice (default `redis://localhost:6379/0`) | your Redis |
| `TEMPORAL_NAMESPACE`, `TEMPORAL_TASK_QUEUE`, `TEMPORAL_WORKFLOW_NAME` | no | must match your Layer 1 worker (defaults `default`, `market-research`, `MarketResearchWorkflow`) |
| `BFF_ORIGIN` | no | the BFF URL (CORS) |
| `DEFAULT_QUARTER` | no | e.g. `2025Q3`, used when a request omits `quarter` |
| `INTERNAL_API_KEY` | only for schedules | `python -c "import secrets;print(secrets.token_urlsafe(32))"` |
| `INNGEST_EVENT_KEY` | no | Inngest dashboard → Event Keys (only to notify Inngest) |
| `CLERK_SECRET_KEY`, `LOG_LEVEL` | no | unused for verification / log level |

**bff_gateway/.env** — all required except `PORT`: `FASTAPI_BASE_URL`, `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY` (Clerk → API Keys), `REDIS_URL`, `ALLOWED_ORIGINS` (frontend origin(s), comma-separated), `NEON_DATABASE_URL`.

## Smoke test (PowerShell)

You need a Clerk session token **with an active organization**. In your frontend's browser console: `await window.Clerk.session.getToken()`. Tokens last ~60 s — refresh as needed.

```powershell
$T = "<paste token>"; $H = @{ Authorization = "Bearer $T" }; $B = "http://localhost:3001"

# 1. health (no token)  -> 200 {"status":"ok","services":{"fastapi":"up","temporal":"up","neon":"up"}}   (503 "degraded" + which one is "down" otherwise)
Invoke-RestMethod "$B/api/health"

# 2. no token -> 401 {"error":"unauthorized",...}
curl.exe -i "$B/api/research/history"

# 3. profile -> {"user":{...},"tenant":{"id":"<uuid>","org_id":"org_...","plan_tier":"free","role":"admin"}}
Invoke-RestMethod "$B/api/user/profile" -Headers $H

# 4. templates -> array of 5 templates
Invoke-RestMethod "$B/api/workflows/templates" -Headers $H

# 5. bad submit -> 422 {"error":"validation_error","details":[{"field":"ticker",...}]}
curl.exe -i -X POST "$B/api/research/submit" -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d '{\"ticker\":\"A B\",\"query\":\"x\"}'

# 6. submit -> 202 {"run_id":"<uuid>","status":"queued","estimated_duration_seconds":420}
$r = Invoke-RestMethod -Method Post "$B/api/research/submit" -Headers $H -ContentType "application/json" -Body '{"ticker":"aapl","quarter":"2025Q3","query":"How did margins trend?","workflow_type":"earnings_analysis"}'
$id = $r.run_id; $r
#    (503 {"detail":"Workflow engine unavailable: Cannot reach Temporal at ..."} if Temporal is down)

# 7. status -> {"run_id":..,"ticker":"AAPL","quarter":"2025Q3","status":"queued|running","current_step":..,"progress_pct":0..100,"started_at":..,"duration_so_far":..}
Invoke-RestMethod "$B/api/research/$id/status" -Headers $H

# 8. live stream (curl.exe, not Invoke-RestMethod) -> lines like "event: connected", "event: step_started", ... ends after "event: report_ready"
curl.exe -N "$B/api/research/$id/stream" -H "Authorization: Bearer $T"

# 9. report -> 409 {"detail":"Report not ready (status=running)"} until done, then the JSON report (full original under "report")
Invoke-RestMethod "$B/api/research/$id/report" -Headers $H
curl.exe "$B/api/research/$id/report?format=pdf" -H "Authorization: Bearer $T" -o report.pdf     # 501 with install hint if Pandoc/LaTeX missing

# 10. history -> {"items":[...],"page":1,"page_size":20,"total":N,"total_pages":M}
Invoke-RestMethod "$B/api/research/history?ticker=AAPL&status=completed" -Headers $H
```
Responses for steps 6, 7, 9 and 10 above are copied from a real run of the test harness (fake Temporal).

## API contract

| Method | Path (through BFF) | Auth | Description |
|---|---|---|---|
| GET | /api/live | no | process is up |
| GET | /api/health | no | fastapi / temporal / neon status |
| GET | /api/user/profile | Clerk | user + tenant |
| POST | /api/research/submit | Clerk (org) | start run; 20/hour per tenant |
| GET | /api/research/history | Clerk (org) | paginated runs; filters ticker, workflow_type, status, date_from, date_to |
| GET | /api/research/{run_id}/status | Clerk (org) | status/progress |
| GET | /api/research/{run_id}/stream | Clerk (org) | SSE, closes on report_ready/failure/35 min |
| GET | /api/research/{run_id}/report | Clerk (org) | report JSON; `?format=pdf` |
| GET | /api/workflows/templates | Clerk (org) | templates |
| GET | /api/workflows/schedules | Clerk (org) | list schedules |
| POST | /api/workflows/schedule | Clerk, org admin | create schedule (cron, UTC) |
| DELETE | /api/workflows/schedule/{id} | Clerk, org admin | deactivate schedule |
| GET | /health (FastAPI, not proxied) | no | neon/redis/temporal |
| POST | /internal/schedules/run-due (FastAPI, not proxied) | `X-Internal-Key` | fire due schedules |

All authenticated routes: 100 requests/minute per user.

## Run the tests (Linux/WSL/macOS only — they start real Postgres and Redis)

```bash
cd agent_service && pip install -r requirements-dev.txt
pytest                      # needs redis-server on PATH; PDF tests need pandoc + xelatex
cd ../bff_gateway && npm install && NEON_DATABASE_URL=... REDIS_URL=... npm test
```
