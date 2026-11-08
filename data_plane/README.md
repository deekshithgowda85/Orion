# Layer 3 — Data & Execution Plane

```
layer3_data_execution_plane/
├── .env.example
├── requirements.txt
├── README.md
└── tools/
    ├── __init__.py
    ├── config.py          # Settings.from_env()
    ├── common.py          # JSON logging, retry/backoff, rate limiter, ToolError, @guarded
    ├── registry.py        # ToolRegistry singleton
    ├── market_data.py     # Polygon (snapshot, financials, options, news) + Redis cache
    ├── sec_filings.py     # EDGAR search/download + LlamaParse section extraction
    ├── scraper.py         # Firecrawl + httpx/BS4 fallback
    ├── quant_sandbox.py   # E2B sandbox, compute_metrics, cross_check_numbers
    ├── vector_store.py    # Neon + pgvector
    ├── scratchpad.py      # per-run Redis scratchpad (gzip >10KB)
    └── injector.py        # LangGraph injector nodes + wire_into_graph()
```

## Run each tool's smoke test (from this folder)
```
pip install -r requirements.txt && cp .env.example .env   # fill keys
python -m tools.market_data     # python -m tools.sec_filings | scraper | quant_sandbox | vector_store | scratchpad | injector
```

## Wire into Layer 2
```python
from tools.registry import ToolRegistry
from tools.injector import ToolInjector

await ToolRegistry.initialize()          # once, at Temporal worker startup
inj = ToolInjector()
inj.wire_into_graph(builder, {           # before builder.compile()
    "market_data": "market_executor",
    "filings": "filings_executor",
    "news": "news_executor",
    "quant": "quant_executor",
})
```
Injector nodes read `ticker`, `run_id`, `tenant_id` (+ optional `quarter`) from state and write
`market_data`, `filings_data`, `news_data`, `quant_data`, `errors`. Order market_data before quant
(quant reads `state["market_data"]`). `python -c "from tools.injector import scan_todo_markers as s; print(s('layer2/'))"`
lists every `# TODO: Layer 3` placeholder.


## Layer 2 integration
See `LAYER2_INTEGRATION.md` (state keys, `wire_before`, single-node `inject_all`).
