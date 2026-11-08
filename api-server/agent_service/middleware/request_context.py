"""Request-ID and structured access-log middleware."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from logging_config import request_id_ctx, run_id_ctx, tenant_id_ctx

access_log = logging.getLogger("access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request_id_ctx.set(rid)
        tenant_id_ctx.set("-")
        run_id_ctx.set(request.path_params.get("run_id", "-") if request.path_params else "-")
        request.state.request_id = rid
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            # run_id lives in the URL path; extract it for the log line
            parts = request.url.path.strip("/").split("/")
            run_id = parts[1] if len(parts) > 1 and parts[0] == "research" and len(parts[1]) == 36 else "-"
            user = getattr(request.state, "user", None)
            access_log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": duration_ms,
                    "run_id": run_id,
                    "tenant_id": str(user.tenant_id) if user else tenant_id_ctx.get(),
                    "request_id": rid,
                },
            )
