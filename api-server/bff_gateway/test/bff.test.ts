/**
 * BFF tests. Real: Express app, http-proxy-middleware, Zod, express-rate-limit + RedisStore, ioredis, real Redis,
 * real Postgres (tenant upsert). Fake: the FastAPI upstream (a local http server) and the Clerk auth stack
 * (Clerk's servers cannot be reached from the sandbox) - injected through createApp({ authStack }).
 */
import assert from "node:assert/strict";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { after, before, describe, it } from "node:test";
import type { NextFunction, Request, Response } from "express";

process.env.FASTAPI_BASE_URL ??= "http://127.0.0.1:1";
process.env.CLERK_SECRET_KEY ??= "sk_test_fake";
process.env.CLERK_PUBLISHABLE_KEY ??= "pk_test_fake";
process.env.ALLOWED_ORIGINS ??= "http://localhost:3000";

interface Seen { method?: string; url?: string; headers: http.IncomingHttpHeaders; body: string }

let upstream: http.Server;
let upstreamUrl = "";
const seen: Seen[] = [];
let bff: http.Server;
let base = "";

function fakeAuth(req: Request, res: Response, next: NextFunction): void {
  // Authorization: Bearer <userId>|<orgId>
  const m = /^Bearer (\w+)\|(\w+)$/.exec(req.headers.authorization ?? "");
  if (!m) { res.status(401).json({ error: "unauthorized" }); return; }
  const [, userId, orgId] = m as unknown as [string, string, string];
  req.tenant = { tenantId: `tenant-${orgId}`, orgId, name: orgId, planTier: "free", userId, orgRole: "org:admin" };
  req.headers["x-tenant-id"] = req.tenant.tenantId;
  req.headers["x-user-id"] = userId;
  next();
}

before(async () => {
  upstream = http.createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => {
      seen.push({ method: req.method, url: req.url, headers: req.headers, body: Buffer.concat(chunks).toString() });
      if (req.url === "/health") { res.setHeader("content-type", "application/json"); res.end(JSON.stringify({ status: "ok", neon: true, redis: true, temporal: true })); return; }
      if (req.url?.endsWith("/stream")) {
        res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
        res.write("event: connected\ndata: {}\n\n");
        setTimeout(() => { res.write("event: step_started\ndata: {\"type\":\"step_started\"}\n\n"); }, 400);
        setTimeout(() => { res.write("event: report_ready\ndata: {}\n\n"); res.end(); }, 900);
        return;
      }
      res.setHeader("content-type", "application/json");
      res.statusCode = req.url === "/research/submit" ? 202 : 200;
      res.end(JSON.stringify({ ok: true, echoed_url: req.url }));
    });
  });
  await new Promise<void>((r) => upstream.listen(0, "127.0.0.1", r));
  upstreamUrl = `http://127.0.0.1:${(upstream.address() as AddressInfo).port}`;
  process.env.FASTAPI_BASE_URL = upstreamUrl;

  const { redis: r0 } = await import("../src/lib/redis");
  const stale = await r0.keys("rl:*");          // rate-limit windows last up to an hour: start each run clean
  if (stale.length) await r0.del(...stale);
  const { createApp } = await import("../src/app");
  bff = createApp({ authStack: [fakeAuth] }).listen(0, "127.0.0.1");
  await new Promise<void>((r) => bff.once("listening", () => r()));
  base = `http://127.0.0.1:${(bff.address() as AddressInfo).port}`;
});

after(async () => {
  bff.closeAllConnections?.();
  bff.close();
  upstream.closeAllConnections?.();
  upstream.close();
  const { redis } = await import("../src/lib/redis");
  const { pool } = await import("../src/lib/db");
  await Promise.allSettled([redis.quit(), pool.end()]);
});

const H = (user = "u1", org = "o1", extra: Record<string, string> = {}) => ({
  authorization: `Bearer ${user}|${org}`, "content-type": "application/json", ...extra,
});

describe("auth / validation / proxy", () => {
  it("rejects unauthenticated /api calls with 401 JSON", async () => {
    const r = await fetch(`${base}/api/research/history`);
    assert.equal(r.status, 401);
    assert.equal((await r.json() as { error: string }).error, "unauthorized");
  });

  it("returns structured 422 for invalid submit bodies and never hits upstream", async () => {
    const before = seen.length;
    const r = await fetch(`${base}/api/research/submit`, {
      method: "POST", headers: H(), body: JSON.stringify({ ticker: "AA PL", query: "x", workflow_type: "bogus", extra: 1 }),
    });
    assert.equal(r.status, 422);
    const j = await r.json() as { error: string; details: { field: string; message: string }[] };
    assert.equal(j.error, "validation_error");
    const fields = j.details.map((d) => d.field);
    for (const f of ["ticker", "query", "workflow_type"]) assert.ok(fields.includes(f), `${f} in ${fields}`);
    assert.equal(seen.length, before);
  });

  it("proxies a valid submit: rewrites path, normalises body, passes quarter, overwrites spoofed tenant headers", async () => {
    const r = await fetch(`${base}/api/research/submit`, {
      method: "POST",
      headers: H("alice", "acme", { "x-tenant-id": "evil-tenant", "x-user-id": "evil-user" }),
      body: JSON.stringify({ ticker: "aapl", quarter: "2025Q3", query: "margin trend please" }),
    });
    assert.equal(r.status, 202);
    const last = seen[seen.length - 1]!;
    assert.equal(last.url, "/research/submit");
    assert.deepEqual(JSON.parse(last.body), {
      ticker: "AAPL", quarter: "2025Q3", query: "margin trend please", workflow_type: "full_research", priority: "normal",
    });
    assert.equal(last.headers["x-tenant-id"], "tenant-acme");
    assert.equal(last.headers["x-user-id"], "alice");
    assert.match(String(last.headers.authorization), /^Bearer alice\|acme$/);   // forwarded so FastAPI can verify the JWT itself
    assert.ok(last.headers["x-request-id"]);
  });

  it("proxies GETs with query strings and workflow routes", async () => {
    const r = await fetch(`${base}/api/research/history?ticker=AAPL&page=2`, { headers: H() });
    assert.equal(r.status, 200);
    assert.equal(seen[seen.length - 1]!.url, "/research/history?ticker=AAPL&page=2");
    const w = await fetch(`${base}/api/workflows/templates`, { headers: H() });
    assert.equal(w.status, 200);
    assert.equal(seen[seen.length - 1]!.url, "/workflows/templates");
  });

  it("validates schedule bodies (422) and forwards valid ones", async () => {
    const bad = await fetch(`${base}/api/workflows/schedule`, {
      method: "POST", headers: H(), body: JSON.stringify({ ticker: "NVDA", workflow_type: "full_research", cron_expr: "every day" }),
    });
    assert.equal(bad.status, 422);
    const ok = await fetch(`${base}/api/workflows/schedule`, {
      method: "POST", headers: H(), body: JSON.stringify({ ticker: "nvda", workflow_type: "full_research", cron_expr: "0 9 * * 1-5" }),
    });
    assert.equal(ok.status, 200);
    assert.equal(JSON.parse(seen[seen.length - 1]!.body).ticker, "NVDA");
  });

  it("answers malformed JSON with 400", async () => {
    const r = await fetch(`${base}/api/research/submit`, { method: "POST", headers: H(), body: "{not json" });
    assert.equal(r.status, 400);
  });

  it("streams SSE through the proxy without buffering", async () => {
    const t0 = Date.now();
    const r = await fetch(`${base}/api/research/abc/stream`, { headers: H() });
    assert.equal(r.status, 200);
    assert.match(r.headers.get("content-type") ?? "", /text\/event-stream/);
    const reader = r.body!.getReader();
    const first = await reader.read();
    const tFirst = Date.now() - t0;
    assert.match(new TextDecoder().decode(first.value), /event: connected/);
    assert.ok(tFirst < 350, `first SSE chunk should arrive immediately, took ${tFirst}ms`);   // upstream only ends at ~900ms
    let rest = "";
    for (;;) { const c = await reader.read(); if (c.done) break; rest += new TextDecoder().decode(c.value); }
    assert.match(rest, /step_started/); assert.match(rest, /report_ready/);
  });

  it("returns 502 JSON when the agent service is down", async () => {
    const { buildProxyRouter } = await import("../src/routes/proxy");
    void buildProxyRouter;
    const express = (await import("express")).default;
    const { env } = await import("../src/config");
    const saved = env.FASTAPI_BASE_URL;
    (env as { FASTAPI_BASE_URL: string }).FASTAPI_BASE_URL = "http://127.0.0.1:1";
    const app = express(); app.use(express.json()); app.use((rq: Request, rs: Response, n: NextFunction) => fakeAuth(rq, rs, n)); app.use(buildProxyRouter());
    const srv = app.listen(0, "127.0.0.1");
    await new Promise<void>((r2) => srv.once("listening", () => r2()));
    const r = await fetch(`http://127.0.0.1:${(srv.address() as AddressInfo).port}/api/research/history`, { headers: H() });
    (env as { FASTAPI_BASE_URL: string }).FASTAPI_BASE_URL = saved;
    srv.close();
    assert.equal(r.status, 502);
    assert.equal((await r.json() as { error: string }).error, "bad_gateway");
  });
});

describe("health", () => {
  it("/api/live is dependency-free and public", async () => {
    const r = await fetch(`${base}/api/live`);
    assert.equal(r.status, 200);
  });
  it("/api/health reports each service; degraded -> 503", async () => {
    const r = await fetch(`${base}/api/health`);
    const j = await r.json() as { status: string; services: Record<string, string> };
    assert.equal(j.services.fastapi, "up");
    assert.equal(j.services.temporal, "up");
    if (process.env.EXPECT_NEON === "up") { assert.equal(j.services.neon, "up"); assert.equal(r.status, 200); }
    else { assert.equal(j.services.neon, "down"); assert.equal(r.status, 503); assert.equal(j.status, "degraded"); }
  });
});

describe("rate limits (real Redis store)", () => {
  it("limits research submissions to 20/hour per tenant (others unaffected)", async () => {
    const body = JSON.stringify({ ticker: "MSFT", query: "rate limit probe" });
    const codes: number[] = [];
    for (let i = 0; i < 22; i++) codes.push((await fetch(`${base}/api/research/submit`, { method: "POST", headers: H("rl_user", "rl_org"), body })).status);
    assert.deepEqual(codes.slice(0, 20), Array(20).fill(202));
    assert.deepEqual(codes.slice(20), [429, 429]);
    const other = await fetch(`${base}/api/research/submit`, { method: "POST", headers: H("rl_user2", "other_org"), body });
    assert.equal(other.status, 202);
  });

  it("limits each user to 100 requests/minute", async () => {
    let last = 0; let firstBlocked = -1;
    for (let i = 1; i <= 103; i++) {
      last = (await fetch(`${base}/api/workflows/templates`, { headers: H("burst_user", "burst_org") })).status;
      if (last === 429 && firstBlocked < 0) firstBlocked = i;
    }
    assert.equal(firstBlocked, 101);
    const r = await fetch(`${base}/api/workflows/templates`, { headers: H("burst_user", "burst_org") });
    assert.equal(r.status, 429);
    assert.equal((await r.json() as { error: string }).error, "rate_limited");
    assert.equal((await fetch(`${base}/api/workflows/templates`, { headers: H("calm_user", "burst_org") })).status, 200);
  });
});

describe("tenant resolution (real Redis cache + real Postgres)", { skip: !process.env.NEON_DATABASE_URL?.includes("host=") && !process.env.REAL_PG }, () => {
  it("creates the tenant once, then serves it from Redis for 300s", async () => {
    const { resolveTenant } = await import("../src/middleware/tenant");
    const { redis } = await import("../src/lib/redis");
    const { pool } = await import("../src/lib/db");
    await redis.del("tenant:meta:org_node_1");
    const a = await resolveTenant("org_node_1");
    const ttl = await redis.ttl("tenant:meta:org_node_1");
    assert.ok(ttl > 290 && ttl <= 300, `ttl=${ttl}`);
    const b = await resolveTenant("org_node_1");
    assert.deepEqual(a, b);
    const { rows } = await pool.query("select id from tenants where clerk_org_id=$1", ["org_node_1"]);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].id, a.tenantId);
  });
});
