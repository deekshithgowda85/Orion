"""Clerk JWT verification (RS256 via JWKS) and request.state.user injection."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware

from config import get_settings
from db import queries
from logging_config import tenant_id_ctx

log = logging.getLogger("auth")

# Paths that never need a Clerk token. /internal/* uses its own shared-secret check.
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}
PUBLIC_PREFIXES = ("/internal/",)


@dataclass
class AuthUser:
    user_id: str
    tenant_id: UUID
    org_id: str
    role: str


_jwk_client: Optional[PyJWKClient] = None


def _jwks() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(get_settings().clerk_jwks_url, cache_keys=True, lifespan=3600, timeout=10)
    return _jwk_client


class AuthProviderUnavailable(Exception):
    """JWKS endpoint could not be reached (not the caller's fault -> 503, not 401)."""


def _decode_sync(token: str) -> dict:
    settings = get_settings()
    try:
        signing_key = _jwks().get_signing_key_from_jwt(token)
    except jwt.PyJWKClientConnectionError as exc:
        raise AuthProviderUnavailable(str(exc)) from exc
    options = {"require": ["exp", "sub"], "verify_aud": False}
    kwargs: dict = {}
    if settings.clerk_issuer:
        kwargs["issuer"] = settings.clerk_issuer
    return jwt.decode(token, signing_key.key, algorithms=["RS256"], options=options, leeway=10, **kwargs)


async def _decode(token: str) -> dict:
    # PyJWKClient does blocking HTTP on a cache miss; keep it off the event loop.
    return await asyncio.to_thread(_decode_sync, token)


async def _resolve_tenant(request: Request, org_id: str) -> UUID:
    """Map Clerk org_id -> tenant UUID (Redis-cached, falls back to the DB if Redis is down)."""
    redis = getattr(request.app.state, "redis", None)
    key = f"tenant:org:{org_id}"
    if redis is not None:
        try:
            cached = await redis.get(key)
            if cached:
                return UUID(cached)
        except Exception:
            log.warning("redis unavailable for tenant cache lookup")
    tenant = await queries.get_or_create_tenant(org_id)
    if redis is not None:
        try:
            await redis.set(key, str(tenant["id"]), ex=300)
        except Exception:
            pass
    return tenant["id"]


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": detail}, headers={"WWW-Authenticate": "Bearer"})


class ClerkAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return _unauthorized("Missing bearer token")

        try:
            claims = await _decode(token)
        except jwt.ExpiredSignatureError:
            return _unauthorized("Token expired")
        except AuthProviderUnavailable:
            log.error("clerk JWKS endpoint unreachable")
            return JSONResponse(status_code=503, content={"detail": "Auth provider (Clerk JWKS) unreachable"})
        except Exception as exc:  # invalid signature, malformed token, wrong issuer, ...
            log.warning("jwt verification failed: %s", exc)
            return _unauthorized("Invalid token")

        # Clerk session token: v1 uses org_id/org_role; v2 nests under claims["o"]
        org = claims.get("o") or {}
        org_id = claims.get("org_id") or org.get("id")
        role = claims.get("org_role") or org.get("rol") or "member"
        if not org_id:
            return _unauthorized("Token has no active organization")
        if role.startswith("org:"):
            role = role[4:]

        try:
            tenant_id = await _resolve_tenant(request, org_id)
        except Exception:
            log.exception("tenant resolution failed")
            return JSONResponse(status_code=503, content={"detail": "Database unavailable"})
        request.state.user = AuthUser(user_id=claims["sub"], tenant_id=tenant_id, org_id=org_id, role=role)
        tenant_id_ctx.set(str(tenant_id))
        return await call_next(request)
