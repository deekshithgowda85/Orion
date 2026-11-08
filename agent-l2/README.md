# Market Research Agent - Layers 1 + 2

Layer 1 = Temporal orchestration + Inngest triggers. Layer 2 = LangGraph agent runtime on Groq (Llama).
Layer 3 (data tools) is NOT included: inject it in `agents/tool_hook.py`.

```
# market-research-agent/
# ├── docker-compose.yml            temporal, temporal-ui, postgres, redis
# ├── .env.example  requirements.txt  config.py  temporal_client.py  worker.py  submit.py
# ├── models/workflow_models.py     all Pydantic v2 models (Layer 1 + Layer 2)
# ├── workflows/research_workflow.py   planner -> executor -> verifier loop -> approval -> synthesis -> audit
# ├── activities/
# │   ├── implementations.py        Layer 2: the 5 real activities (registered by worker.py)
# │   ├── audit_store.py            Neon table workflow_traces
# │   └── stubs.py                  Layer 1 stubs (kept for the trace helper)
# ├── agents/
# │   ├── state.py                  AgentState, MAX_ITERATIONS = 5
# │   ├── planner.py  parallel_executor.py  verifier.py  synthesizer.py
# │   ├── executors/                market_data / filings / quant / news (+ common.py)
# │   ├── graph.py                  StateGraph + run_research_graph(request) -> FinalReport
# │   ├── tool_hook.py              <-- Layer 3 plugs real tool output in here
# │   ├── claims.py  settings.py  mock_data.py
# ├── llm/groq_client.py            async Groq, forced tool-calling, Pydantic validation + self-repair
# ├── prompts/templates.py          PLANNER_SYSTEM ... SYNTHESIS_SYSTEM
# ├── inngest_triggers/             trigger.py, server.py
# └── tests/test_offline.py         no API key / server needed
```

## Models
`MODEL_LARGE` (planner, quant, verifier, synthesis) defaults to `llama-3.3-70b-versatile`;
`MODEL_FAST` (market data, filings, news extraction) defaults to `llama-3.1-8b-instant`.
Override with `GROQ_MODEL_LARGE` / `GROQ_MODEL_FAST` in `.env`.

## Run (Windows PowerShell)
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env        # then put your GROQ_API_KEY in .env

python -m tests.test_offline       # offline checks, no key needed

# standalone agent demos (need GROQ_API_KEY; use synthetic ACME fixtures)
python -m agents.planner
python -m agents.executors.market_data_executor
python -m agents.graph             # full graph incl. self-correction loop

# full stack
docker compose up -d
python worker.py
uvicorn inngest_triggers.server:app --port 8000
python submit.py start --ticker AAPL --query "Audit AAPL margins" --type deep_audit
```
Until Layer 3 replaces `tool_hook.get_tool_output`, real runs get no data: executors return nothing,
the verifier skips re-querying, and the report says no verifiable data was found (confidence 0).
