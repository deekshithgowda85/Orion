"""FastAPI app exposing the Inngest functions: ``uvicorn inngest_triggers.server:app --port 8000``."""
import inngest.fast_api
from fastapi import FastAPI

from inngest_triggers.trigger import FUNCTIONS, inngest_client

app = FastAPI(title="Market Research - Inngest triggers")
inngest.fast_api.serve(app, inngest_client, FUNCTIONS)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
