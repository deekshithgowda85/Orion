# Market Research Agent - Layer 1: Workflow Orchestration

```
# market-research-agent/
# ├── docker-compose.yml          temporal, temporal-ui, postgres, redis
# ├── .env.example
# ├── requirements.txt
# ├── config.py                   settings + shared constants
# ├── temporal_client.py          client + idempotent start_research()
# ├── worker.py                   Temporal worker (market-research-queue)
# ├── submit.py                   CLI: start / approve / stage
# ├── models/workflow_models.py   all Pydantic v2 models
# ├── activities/stubs.py         5 activities (Layer 2 fills them in)
# ├── workflows/research_workflow.py
# └── inngest_triggers/
#     ├── trigger.py              query.submitted + 07:00 UTC weekday cron
#     └── server.py               FastAPI app that serves the Inngest functions
```

## Run it (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env

docker compose up -d
docker compose ps            # wait until temporal shows (healthy)

python worker.py                                          # terminal 1
uvicorn inngest_triggers.server:app --port 8000           # terminal 2
npx inngest-cli@latest dev -u http://localhost:8000/api/inngest   # terminal 3
```

Temporal UI: http://localhost:8080 - Inngest dev UI: http://localhost:8288

Start a run without Inngest:

```powershell
python submit.py start --ticker AAPL --query "Audit AAPL services margin trend" --type deep_audit
python submit.py stage  <workflow_id>
python submit.py approve <workflow_id>
```

Via Inngest (webhook event):

```powershell
$body = @{ name = "market-research/query.submitted"; data = @{
  ticker = "NVDA"; query = "Earnings pulse for NVDA"; workflow_type = "earnings_pulse"; tenant_id = "demo-tenant" } } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri "http://localhost:8288/e/dev" -ContentType "application/json" -Body $body
```

Stop: `docker compose down` (add `-v` to wipe data).

## Expected behaviour in Layer 1

Activities are stubs, so a run fails at PlannerActivity with `NotImplementedError`
(marked non-retryable so it fails fast). The failed trace event is logged by the worker.
Layer 2 replaces each stub body and returns `<Output>(..., trace=rec.success())`.
