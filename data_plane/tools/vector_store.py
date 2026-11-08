"""Neon (Postgres) + pgvector store. Raw scraped content lives here, never in LLM context."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Callable

import httpx
import psycopg2
from psycopg2.extras import Json, RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool
from pydantic import BaseModel, Field

from .common import ToolError, get_logger, guarded, is_retryable, log_event, with_retry

log = get_logger("vector_store")

EMBED_DIM = 1536
EMBED_BATCH = 64

SETUP_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS embeddings_run_idx ON embeddings (run_id);
CREATE INDEX IF NOT EXISTS embeddings_tenant_ticker_idx ON embeddings (tenant_id, (metadata->>'ticker'));
CREATE INDEX IF NOT EXISTS embeddings_hnsw_idx ON embeddings USING hnsw (embedding vector_cosine_ops);
"""


class VectorStoreError(ToolError):
    pass


class RetrievedChunk(BaseModel):
    id: str
    run_id: str
    chunk_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None  # cosine similarity (1 = identical); None for non-ranked lookups
    created_at: datetime | None = None


def _db_retryable(exc: BaseException) -> bool:
    return isinstance(exc, psycopg2.OperationalError) or is_retryable(exc)  # Neon cold starts


def _vec(v: list[float]) -> str:
    return "[" + ",".join(format(x, ".7g") for x in v) + "]"


class VectorStore:
    def __init__(self, dsn: str, openai_api_key: str, embedding_model: str = "text-embedding-3-small",
                 min_conn: int = 1, max_conn: int = 5) -> None:
        self._dsn = dsn
        self._model = embedding_model
        self._http = httpx.AsyncClient(
            base_url="https://api.openai.com/v1", timeout=httpx.Timeout(60.0),
            headers={"Authorization": f"Bearer {openai_api_key}"})
        self._min, self._max = min_conn, max_conn
        self._pool: ThreadedConnectionPool | None = None
        self._pool_lock = asyncio.Lock()

    # ---- lifecycle
    async def connect(self) -> None:
        async with self._pool_lock:
            if self._pool is None:
                async def attempt() -> ThreadedConnectionPool:
                    return await asyncio.to_thread(ThreadedConnectionPool, self._min, self._max, self._dsn)

                self._pool = await with_retry(attempt, op="neon.connect", logger=log, retryable=_db_retryable)

    async def close(self) -> None:
        await self._http.aclose()
        if self._pool is not None:
            await asyncio.to_thread(self._pool.closeall)
            self._pool = None

    @guarded("neon.ensure_schema", VectorStoreError)
    async def ensure_schema(self) -> None:
        await self._db("neon.ensure_schema", lambda cur: cur.execute(SETUP_SQL))
        log_event(log, logging.INFO, "vector_schema_ready")

    # ---- plumbing
    async def _db(self, op: str, fn: Callable[[Any], Any]) -> Any:
        if self._pool is None:
            await self.connect()
        pool = self._pool

        def run() -> Any:
            conn = pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    result = fn(cur)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
            finally:
                pool.putconn(conn)

        async def attempt() -> Any:
            return await asyncio.to_thread(run)

        return await with_retry(attempt, op=op, logger=log, retryable=_db_retryable)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            payload: dict[str, Any] = {"model": self._model, "input": batch}
            if self._model.startswith("text-embedding-3"):
                payload["dimensions"] = EMBED_DIM

            async def attempt() -> httpx.Response:
                resp = await self._http.post("/embeddings", json=payload)
                resp.raise_for_status()
                return resp

            resp = await with_retry(attempt, op="openai.embeddings", logger=log, ctx={"batch": len(batch)})
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            for d in data:
                if len(d["embedding"]) != EMBED_DIM:
                    raise VectorStoreError(f"embedding dim {len(d['embedding'])} != {EMBED_DIM}")
                out.append(d["embedding"])
        return out

    @staticmethod
    def chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> list[str]:
        """Paragraph-aware splitter with character overlap."""
        text = text.strip()
        if not text:
            return []
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        buf = ""
        for p in paras:
            while len(p) > max_chars:  # hard-split oversized paragraphs
                if buf:
                    chunks.append(buf)
                    buf = ""
                chunks.append(p[:max_chars])
                p = p[max_chars - overlap:]
            if len(buf) + len(p) + 2 <= max_chars:
                buf = f"{buf}\n\n{p}" if buf else p
            else:
                if buf:
                    chunks.append(buf)
                tail = buf[-overlap:] if overlap and buf else ""
                buf = f"{tail}\n\n{p}".strip() if tail else p
        if buf:
            chunks.append(buf)
        return chunks

    # ---- public API
    @guarded("neon.embed_and_store", VectorStoreError)
    async def embed_and_store(self, chunks: list[str], metadata: dict[str, Any] | list[dict[str, Any]],
                              run_id: str, tenant_id: str) -> None:
        """`metadata` is applied to every chunk (dict) or per-chunk (list matching `chunks`)."""
        metas = metadata if isinstance(metadata, list) else [metadata] * len(chunks)
        if len(metas) != len(chunks):
            raise VectorStoreError("metadata list length must match chunks")
        pairs = [(c, m) for c, m in zip(chunks, metas) if c and c.strip()]
        if not pairs:
            return
        vectors = await self._embed([c for c, _ in pairs])
        rows = [(run_id, tenant_id, c, Json(m), _vec(v)) for (c, m), v in zip(pairs, vectors)]

        def insert(cur: Any) -> None:
            execute_values(
                cur,
                "INSERT INTO embeddings (id, run_id, tenant_id, chunk_text, metadata, embedding) VALUES %s",
                rows, template="(gen_random_uuid(), %s, %s, %s, %s, %s::vector)", page_size=100)

        await self._db("neon.insert_embeddings", insert)
        log_event(log, logging.INFO, "embeddings_stored", run_id=run_id, tenant_id=tenant_id, chunks=len(rows))

    @guarded("neon.ingest_text", VectorStoreError)
    async def ingest_text(self, text: str, metadata: dict[str, Any], run_id: str, tenant_id: str) -> int:
        """Chunk + embed + store; returns number of chunks. Use this for scraped pages and filing sections."""
        chunks = self.chunk_text(text)
        await self.embed_and_store(chunks, metadata, run_id, tenant_id)
        return len(chunks)

    @guarded("neon.store_finding", VectorStoreError)
    async def store_finding(self, ticker: str, text: str, run_id: str, tenant_id: str,
                            extra: dict[str, Any] | None = None) -> int:
        """Persist an agent conclusion so future runs can surface it via get_past_findings()."""
        meta = {"ticker": ticker.upper(), "kind": "finding", **(extra or {})}
        return await self.ingest_text(text, meta, run_id, tenant_id)

    @guarded("neon.similarity_search", VectorStoreError)
    async def similarity_search(self, query: str, run_id: str, top_k: int = 10,
                                tenant_id: str | None = None,
                                metadata_filter: dict[str, Any] | None = None) -> list[RetrievedChunk]:
        if not query.strip():
            raise VectorStoreError("query must not be empty")
        qv = _vec((await self._embed([query]))[0])
        where, params = ["run_id = %s"], [run_id]
        if tenant_id:
            where.append("tenant_id = %s")
            params.append(tenant_id)
        if metadata_filter:
            where.append("metadata @> %s")
            params.append(Json(metadata_filter))
        sql = (f"SELECT id::text, run_id, chunk_text, metadata, created_at, "
               f"1 - (embedding <=> %s::vector) AS score FROM embeddings WHERE {' AND '.join(where)} "
               f"ORDER BY embedding <=> %s::vector LIMIT %s")
        full_params = [qv, *params, qv, top_k]

        def select(cur: Any) -> list[dict[str, Any]]:
            cur.execute(sql, full_params)
            return cur.fetchall()

        rows = await self._db("neon.similarity_search", select)
        return [RetrievedChunk(**r) for r in rows]

    @guarded("neon.get_past_findings", VectorStoreError)
    async def get_past_findings(self, ticker: str, tenant_id: str, limit: int = 5) -> list[RetrievedChunk]:
        """Most recent stored findings (kind='finding') for this tenant + ticker, across runs."""
        sql = ("SELECT id::text, run_id, chunk_text, metadata, created_at FROM embeddings "
               "WHERE tenant_id = %s AND metadata->>'ticker' = %s AND metadata->>'kind' = 'finding' "
               "ORDER BY created_at DESC LIMIT %s")

        def select(cur: Any) -> list[dict[str, Any]]:
            cur.execute(sql, (tenant_id, ticker.upper(), limit))
            return cur.fetchall()

        rows = await self._db("neon.get_past_findings", select)
        return [RetrievedChunk(**r) for r in rows]

    @guarded("neon.delete_run", VectorStoreError)
    async def delete_run(self, run_id: str, tenant_id: str) -> int:
        def delete(cur: Any) -> int:
            cur.execute("DELETE FROM embeddings WHERE run_id = %s AND tenant_id = %s", (run_id, tenant_id))
            return cur.rowcount

        return await self._db("neon.delete_run", delete)


# --------------------------------------------------------------------------- smoke test
async def _demo() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    dsn, key = os.environ.get("NEON_DATABASE_URL"), os.environ.get("OPENAI_API_KEY")
    if not (dsn and key):
        print("NEON_DATABASE_URL / OPENAI_API_KEY not set — skipping live test")
        print("chunk_text sample:", [len(c) for c in VectorStore.chunk_text("para one.\n\n" * 400)][:5])
        return
    vs = VectorStore(dsn, key, os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"))
    try:
        await vs.ensure_schema()
        n = await vs.ingest_text("Apple reported record services revenue.\n\nSupply chain risk remains in Asia.",
                                 {"ticker": "AAPL", "kind": "demo"}, "demo-run", "demo-tenant")
        print("stored chunks:", n)
        hits = await vs.similarity_search("supply chain risk", "demo-run", top_k=3, tenant_id="demo-tenant")
        for h in hits:
            print(round(h.score or 0, 3), h.chunk_text[:80].replace("\n", " "))
        await vs.store_finding("AAPL", "Demo finding: services margin expanding.", "demo-run", "demo-tenant")
        print("past findings:", len(await vs.get_past_findings("AAPL", "demo-tenant")))
        print("deleted:", await vs.delete_run("demo-run", "demo-tenant"))
    finally:
        await vs.close()


if __name__ == "__main__":
    asyncio.run(_demo())
