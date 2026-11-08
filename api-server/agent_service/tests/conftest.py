"""Test harness: REAL PostgreSQL 16 (embedded) + REAL redis-server + locally signed RS256 JWTs.
Only Temporal is faked (no Temporal server available) and the Clerk JWKS endpoint is replaced by a local key.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
REDIS_PORT = 6391


def _wait_port(port: int, timeout: float = 10) -> None:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"port {port} never opened")


@pytest.fixture(scope="session", autouse=True)
def infra():
    import pixeltable_pgserver as pg

    tmp = tempfile.mkdtemp(prefix="l4test-")
    pgsrv = pg.get_server(os.path.join(tmp, "pg"), cleanup_mode="delete")
    dsn = pgsrv.get_uri()
    schema = (ROOT / "db" / "schema.sql").read_text()
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(schema)          # applies the REAL schema.sql
        c.execute(schema)          # and proves it is re-runnable (idempotent)

    redis_proc = subprocess.Popen(
        ["redis-server", "--port", str(REDIS_PORT), "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    _wait_port(REDIS_PORT)

    os.environ.update(
        NEON_DATABASE_URL=dsn,
        REDIS_URL=f"redis://127.0.0.1:{REDIS_PORT}/0",
        CLERK_JWKS_URL="https://example.invalid/.well-known/jwks.json",
        CLERK_ISSUER="https://clerk.test",
        INTERNAL_API_KEY="test-internal-key",
        TEMPORAL_HOST="localhost:7233",
        SSE_STATUS_POLL_SECONDS="0.5",
        BFF_ORIGIN="http://localhost:3001",
    )
    yield SimpleNamespace(dsn=dsn)
    redis_proc.terminate()
    pgsrv.cleanup()
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- JWT helpers
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(org_id: str | None = "org_A", role: str = "org:admin", sub: str = "user_1",
               exp_delta: int = 3600, key=_KEY, issuer: str = "https://clerk.test") -> str:
    claims = {"sub": sub, "exp": int(time.time()) + exp_delta, "iat": int(time.time()) - 5, "iss": issuer}
    if org_id:
        claims.update(org_id=org_id, org_role=role)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def auth(org_id="org_A", role="org:admin", **kw) -> dict:
    return {"Authorization": f"Bearer {make_token(org_id, role, **kw)}"}


class FakeTemporal:
    """Records start_workflow calls exactly like temporalio.client.Client.start_workflow."""

    def __init__(self) -> None:
        self.started: list[dict] = []
        self.fail = False
        self.service_client = SimpleNamespace(check_health=self._ok)

    async def _ok(self):
        return True

    async def start_workflow(self, name, arg, **kw):
        if self.fail:
            raise RuntimeError("simulated temporal failure")
        self.started.append({"name": name, "arg": arg, **kw})
        return SimpleNamespace(id=kw["id"])


@pytest.fixture()
def fake_temporal(monkeypatch):
    ft = FakeTemporal()
    from services import temporal_service

    async def _connect():
        return ft

    monkeypatch.setattr(temporal_service, "connect", _connect)
    return ft


@pytest.fixture()
def client(fake_temporal, monkeypatch):
    import middleware.auth as auth_mod
    monkeypatch.setattr(auth_mod, "_jwks", lambda: SimpleNamespace(
        get_signing_key_from_jwt=lambda tok: SimpleNamespace(key=_KEY.public_key())))
    from fastapi.testclient import TestClient
    from main import create_app
    with TestClient(create_app()) as c:   # runs the real lifespan: pool, redis, event sink
        yield c
