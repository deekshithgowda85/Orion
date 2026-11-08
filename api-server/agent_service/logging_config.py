"""JSON structured logging with request-scoped context (run_id, tenant_id, duration_ms)."""
import contextvars
import logging
import sys

from pythonjsonlogger import jsonlogger

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
tenant_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="-")
run_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="-")


class ContextFilter(logging.Filter):
    """Adds request_id/tenant_id/run_id from context vars, but never overwrites
    values passed explicitly via `extra=` (the access log passes its own)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_ctx.get()
        if not hasattr(record, "tenant_id"):
            record.tenant_id = tenant_id_ctx.get()
        if not hasattr(record, "run_id"):
            record.run_id = run_id_ctx.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(tenant_id)s %(run_id)s",
            rename_fields={"asctime": "ts", "levelname": "level"},
        )
    )
    handler.addFilter(ContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = True
