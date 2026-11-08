# LAYER4_INTEGRATION.md — edits needed in Layers 1, 2 and 3

Layer 4 makes **no imports** from other layers (verified by a test: no `ToolRegistry`/`ToolInjector` references).
It talks to them only through four contracts. Everything below is something *you* must do or confirm.

## Contract 1 — Temporal workflow start (Layer 1)

Layer 4 calls `client.start_workflow(TEMPORAL_WORKFLOW_NAME, <one dict>, id="research-<run_id>", task_queue=TEMPORAL_TASK_QUEUE)`.

| Setting | Default | Must match |
|---|---|---|
| `TEMPORAL_WORKFLOW_NAME` | `MarketResearchWorkflow` | the name your worker registers |
| `TEMPORAL_TASK_QUEUE` | `market-research` | the queue your worker polls |

The single dict argument (built in `agent_service/services/temporal_service.py::build_workflow_input` — the only place to edit if your signature differs):

```json
{
  "run_id": "uuid", "tenant_id": "uuid", "user_id": "clerk user id",
  "ticker": "AAPL", "quarter": "2025Q3" | null,
  "query": "...", "workflow_type": "full_research|earnings_analysis|...", "priority": "low|normal|high",
  "agent_state": { "ticker": "AAPL", "quarter": "2025Q3", "errors": [], "run_id": "uuid" }
}
```

**Layer 1 edits**
1. Accept this dict (a dataclass/pydantic model with these fields works with Temporal's default converter), or edit `build_workflow_input`.
2. Seed the LangGraph `AgentState` from `agent_state` (ticker, quarter, errors).
3. `quarter` is **optional** in the API (`null` if omitted and `DEFAULT_QUARTER` is empty). If Layer 3 requires a quarter, either require it in Layer 3 with a clear error, or set `DEFAULT_QUARTER`. Layer 4 does not interpret the format (only `[A-Za-z0-9 _-]{1,16}`).
4. Persist results with `integration/run_store.py` (copy it into the worker project; needs `psycopg[binary]` + `NEON_DATABASE_URL`):
   - at start: `mark_running(run_id)` (optional — the first progress event also does it)
   - citations: `save_citation(run_id, ...)`
   - at the end: `save_report(run_id, report_dict)` **then** `publish_report_ready(run_id)`
   - on failure (Temporal activity/workflow `except`): `mark_failed(run_id, str(exc))`
   If nothing calls `save_report`, `/status` stays `running` and `/report` returns 409 forever.

## Contract 2 — Progress events (Layer 2, LangGraph)

Copy **one file**: `agent_service/integration/progress_events.py` (needs only `pip install redis`; reads `REDIS_URL`).

1. Decorate each node: `@with_progress_events("<node name>")`. Works for sync and async nodes, and for nodes with or without a `config` parameter (the wrapper always exposes `config` so LangGraph passes it).
2. Make `run_id` reachable — **Layer 3's AgentState has no `run_id`** (ticker, quarter, market_data, filings_data, news_data, quant_data, errors). Pick one:
   - add `run_id: str` to `AgentState` (recommended; LangGraph silently drops undeclared input keys — proven by a test), or
   - call `graph.ainvoke(state, {"configurable": {"run_id": run_id}})`, or
   - set the `RUN_ID` environment variable for one-process-per-run workers.
   With none of these, the decorator does nothing and never raises (progress just won't show).
3. Call `register_steps([...your real node names in order...])` once at import time so `progress_pct` is meaningful. Without it events carry no percentage and `/status` only shows `current_step`.
4. LangGraph forbids a node name equal to a state key — name nodes e.g. `fetch_market`, not `market_data` (found while testing).
5. To emit `conflict_found`, return `{"conflicts": [ {...}, ... ]}` from a node (include `conflicts` in the state/return schema if you want it kept in state; the decorator reads the node's return value).
6. After the report is saved: `publish_report_ready(run_id, summary)`. If you forget, the SSE stream still ends within ~5 s of the DB status becoming `completed`/`failed`.

Channel: `run:{run_id}:events`; message `{"type","payload","ts"}`. Layer 4 also mirrors `step_started`/`step_completed` into `workflow_runs.current_step/progress_pct`.

## Contract 3 — Neon schema

Apply `agent_service/db/schema.sql` (idempotent; includes `ALTER TABLE ... IF NOT EXISTS` for DBs created from the first version). Layer 1–3 must not create their own `workflow_runs` table. Requires PostgreSQL 13+ (`gen_random_uuid()`), no extensions.

`report_jsonb` may have **any shape**. `/report` returns it untouched under `report`, and also maps `summary` (or `executive_summary`), `sections`, `conflicts`, `metadata` if present. PDF export renders unknown shapes as one section per top-level key.

## Contract 4 — Redis

Same Redis instance as Layers 1–3 is fine (key prefixes `run:`, `tenant:`, `rl:`). Not needed to run Layer 4: Polygon, EDGAR, Firecrawl, E2B, Pgvector keys (those belong to Layers 2–3).

## Scheduling (Inngest) — what changed

The first version called Inngest REST endpoints that do not exist. Now: schedules live in Neon; `POST /internal/schedules/run-due` (header `X-Internal-Key: $INTERNAL_API_KEY`) fires due ones. Call it every minute from an Inngest cron function, cron, or Windows Task Scheduler. Inngest function sketch (TypeScript):

```ts
inngest.createFunction({ id: "tick-schedules" }, { cron: "* * * * *" }, async () => {
  await fetch(`${process.env.AGENT_URL}/internal/schedules/run-due`, { method: "POST",
    headers: { "X-Internal-Key": process.env.INTERNAL_API_KEY! } });
});
```
This sketch was **not run** (no Inngest account in the sandbox).
