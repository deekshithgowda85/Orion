"""Per-run Redis scratchpad. Keys: scratchpad:{run_id}:<key>. Values >10KB are gzip-compressed."""
from __future__ import annotations

import asyncio
import gzip
import json
import os
from typing import Any

import redis.asyncio as aioredis

from .common import ToolError, get_logger, guarded

log = get_logger("scratchpad")

COMPRESS_THRESHOLD = 10 * 1024
_GZ, _RAW = b"gz:", b"js:"


class ScratchpadError(ToolError):
    pass


def encode_value(value: Any) -> bytes:
    raw = json.dumps(value, default=str).encode("utf-8")
    if len(raw) > COMPRESS_THRESHOLD:
        return _GZ + gzip.compress(raw)
    return _RAW + raw


def decode_value(blob: bytes | str) -> Any:
    if isinstance(blob, str):  # client created with decode_responses=True would break gzip payloads
        raise ScratchpadError("Redis client must be created with decode_responses=False")
    if blob.startswith(_GZ):
        return json.loads(gzip.decompress(blob[len(_GZ):]))
    if blob.startswith(_RAW):
        return json.loads(blob[len(_RAW):])
    raise ScratchpadError("unrecognised scratchpad payload")


class Scratchpad:
    def __init__(self, redis: aioredis.Redis, run_id: str) -> None:
        if not run_id:
            raise ValueError("run_id is required")
        self._r = redis
        self.run_id = run_id

    @property
    def prefix(self) -> str:
        return f"scratchpad:{self.run_id}:"

    def _k(self, key: str) -> str:
        return f"{self.prefix}{key}"

    @guarded("scratchpad.set", ScratchpadError)
    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        await self._r.set(self._k(key), encode_value(value), ex=ttl)

    @guarded("scratchpad.get", ScratchpadError)
    async def get(self, key: str) -> Any | None:
        blob = await self._r.get(self._k(key))
        return None if blob is None else decode_value(blob)

    @guarded("scratchpad.append_to_list", ScratchpadError)
    async def append_to_list(self, key: str, item: Any, ttl: int = 3600) -> int:
        k = self._k(key)
        async with self._r.pipeline(transaction=True) as pipe:
            pipe.rpush(k, encode_value(item))
            pipe.expire(k, ttl)
            length, _ = await pipe.execute()
        return int(length)

    @guarded("scratchpad.get_list", ScratchpadError)
    async def get_list(self, key: str) -> list[Any]:
        return [decode_value(b) for b in await self._r.lrange(self._k(key), 0, -1)]

    @guarded("scratchpad.clear_run", ScratchpadError)
    async def clear_run(self, run_id: str | None = None) -> int:
        prefix = f"scratchpad:{run_id or self.run_id}:"
        deleted = 0
        batch: list[bytes] = []
        async for k in self._r.scan_iter(match=f"{prefix}*", count=500):
            batch.append(k)
            if len(batch) >= 500:
                deleted += await self._r.delete(*batch)
                batch.clear()
        if batch:
            deleted += await self._r.delete(*batch)
        return deleted


# --------------------------------------------------------------------------- smoke test
async def _demo() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    url = os.environ.get("REDIS_URL")
    if not url:
        print("REDIS_URL not set — skipping live test")
        return
    r = aioredis.from_url(url, decode_responses=False)
    sp = Scratchpad(r, "demo-run")
    await sp.set("small", {"a": 1})
    await sp.set("big", {"blob": "x" * 50_000})
    await sp.append_to_list("events", {"n": 1})
    await sp.append_to_list("events", {"n": 2})
    big = await sp.get("big")
    stored = await r.get(sp._k("big"))
    print("small:", await sp.get("small"))
    print("big roundtrip ok:", len(big["blob"]) == 50_000, "| stored bytes:", len(stored), "| gz:", stored.startswith(b"gz:"))
    print("list:", await sp.get_list("events"))
    print("cleared keys:", await sp.clear_run("demo-run"))
    await r.aclose()


if __name__ == "__main__":
    asyncio.run(_demo())
