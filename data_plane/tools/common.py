"""Shared helpers: structured logging, retry/backoff, rate limiting, error types."""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import random
import sys
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, TypeVar

import httpx

T = TypeVar("T")


# --------------------------------------------------------------------------- logging
class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if fields:
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    root = logging.getLogger("layer3")
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFormatter())
        root.addHandler(handler)
        root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
        root.propagate = False
    return logging.getLogger(f"layer3.{name}")


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    logger.log(level, event, extra={"fields": fields})


# --------------------------------------------------------------------------- errors
class ToolError(RuntimeError):
    """Base class for all Layer 3 tool failures."""


def guarded(op: str, error_cls: type[ToolError] = ToolError):
    """Wrap an async method: log failures in structured form and re-raise as a ToolError."""

    def deco(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        logger = get_logger("guard")

        @functools.wraps(fn)
        async def wrapper(self, *args, **kwargs):
            try:
                return await fn(self, *args, **kwargs)
            except ToolError:
                raise
            except Exception as exc:  # noqa: BLE001
                log_event(logger, logging.ERROR, "tool_call_failed", op=op,
                          error=repr(exc), error_type=type(exc).__name__)
                raise error_cls(f"{op} failed: {exc}") from exc

        return wrapper

    return deco


# --------------------------------------------------------------------------- misc helpers
def g(obj: Any, name: str, default: Any = None) -> Any:
    """Read `name` from a dict or an object attribute; tolerant of SDK model changes."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def to_float(x: Any) -> float | None:
    try:
        if x is None or isinstance(x, bool):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def make_soup(html: str):
    from bs4 import BeautifulSoup, FeatureNotFound

    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(html, "html.parser")


# --------------------------------------------------------------------------- retry
_RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
_RETRY_TOKENS = (
    "429", "too many requests", "rate limit", "rate-limit", "ratelimit", "temporarily unavailable",
    "timed out", "timeout", "connection reset", "connection aborted", "connection refused",
    " 500", " 502", " 503", " 504", "server closed the connection",
)


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRY_STATUS
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError, ConnectionError, TimeoutError)):
        return True
    msg = str(exc).lower()
    return any(tok in msg for tok in _RETRY_TOKENS)


def _retry_after(exc: BaseException) -> float | None:
    if isinstance(exc, httpx.HTTPStatusError):
        val = exc.response.headers.get("retry-after")
        try:
            return float(val) if val else None
        except ValueError:
            return None
    return None


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    op: str,
    logger: logging.Logger,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
    retryable: Callable[[BaseException], bool] = is_retryable,
    ctx: dict[str, Any] | None = None,
) -> T:
    """Exponential backoff with jitter; at most `max_retries` retries (max_retries+1 attempts)."""
    ctx = ctx or {}
    attempt = 0
    while True:
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            if attempt >= max_retries or not retryable(exc):
                log_event(logger, logging.ERROR, "external_call_failed", op=op, attempt=attempt + 1,
                          error=repr(exc), error_type=type(exc).__name__, **ctx)
                raise
            delay = min(max_delay, base_delay * (2 ** attempt)) + random.uniform(0, 0.25 * base_delay)
            ra = _retry_after(exc)
            if ra is not None:
                delay = min(max_delay, max(delay, ra))
            log_event(logger, logging.WARNING, "external_call_retry", op=op, attempt=attempt + 1,
                      next_delay_s=round(delay, 2), error=repr(exc), **ctx)
            await asyncio.sleep(delay)
            attempt += 1


# --------------------------------------------------------------------------- rate limiter
class AsyncRateLimiter:
    """Sliding-window limiter: at most `max_calls` per `period` seconds."""

    def __init__(self, max_calls: int, period: float = 1.0) -> None:
        self._max = max_calls
        self._period = period
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self._period:
                    self._calls.popleft()
                if len(self._calls) < self._max:
                    self._calls.append(now)
                    return
                await asyncio.sleep(max(self._period - (now - self._calls[0]), 0.001))
