# Plugging Layer 3 into Layer 2 (3 edits in Layer 2)

## 1. State: add `ticker`, `quarter`, the four data keys, and `errors` (with a reducer)
In Layer 2's `AgentState` (LangGraph drops any key that is not declared here):

```python
import operator
from typing import Annotated, Any, TypedDict

class AgentState(TypedDict, total=False):
    # ... your existing keys (run_id, tenant_id, query, task_graph, tool_results, ...) ...
    ticker: str                      # NEW - Layer 3 needs it
    quarter: str                     # NEW - optional, e.g. "Q3 2025" (earnings transcript)
    market_data: dict[str, Any]      # NEW - written by Layer 3
    filings_data: dict[str, Any]     # NEW
    news_data: dict[str, Any]        # NEW
    quant_data: dict[str, Any]       # NEW
    errors: Annotated[list[dict[str, Any]], operator.add]   # NEW - reducer is required
```

## 2. Initial state: copy the ticker from the request
Where Layer 2 builds the starting state (e.g. in `run_research_graph`):

```python
initial_state = {
    "run_id": request.run_id, "tenant_id": request.tenant_id, "query": request.query,
    "ticker": request.ticker,                       # NEW
    "quarter": getattr(request, "quarter", None),   # NEW (optional)
    # ... rest unchanged ...
}
```

## 3. Graph: insert the injector before the executor(s)
Layer 2 with ONE `parallel_executor` node (as in the Layer 2 prompt):

```python
from layer3_data_execution_plane.tools.injector import ToolInjector
from layer3_data_execution_plane.tools.registry import ToolRegistry

registry = await ToolRegistry.initialize()          # once, at worker start
injector = ToolInjector(registry=registry)

builder = StateGraph(AgentState)
# ... add_node / add_edge exactly as before ...
injector.wire_before(builder, "parallel_executor")  # BEFORE builder.compile()
graph = builder.compile()
```

If you instead built four separate executor nodes, use
`injector.wire_into_graph(builder, {"market_data": "<node>", "filings": "<node>", "news": "<node>", "quant": "<node>"})`
with your real node names.

## 4. Executors: read the new keys
Replace the placeholder/TODO data in each executor with `state["market_data"]`, `state["filings_data"]`,
`state["news_data"]`, `state["quant_data"]`.

## Behaviour to know
- If the verifier loops back to the planner, `inject_all` sees the data is already in state and does nothing,
  so filings are not downloaded and embedded again.
- A failing source never crashes the graph: that key gets `status: "error"` and the reason is appended to `errors`.
- `errors` must use the `operator.add` reducer. Injector nodes return only their new errors.
