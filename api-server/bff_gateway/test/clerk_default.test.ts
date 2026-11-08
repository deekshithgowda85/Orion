/** Default (real Clerk) auth stack with FAKE keys: proves unauthenticated/garbage-token requests get a clean 401 JSON
 *  (not a redirect or 500). Cannot prove a *valid* Clerk token works - that needs real Clerk keys. */
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { after, before, describe, it } from "node:test";

process.env.FASTAPI_BASE_URL ??= "http://127.0.0.1:1";
process.env.CLERK_SECRET_KEY = "sk_test_FAKE_FOR_TESTS_ONLY";
process.env.CLERK_PUBLISHABLE_KEY = "pk_test_Y2xlcmsuZXhhbXBsZS5jb20k";
process.env.ALLOWED_ORIGINS ??= "http://localhost:3000";

let srv: import("node:http").Server; let base = "";
before(async () => {
  const { createApp } = await import("../src/app");
  srv = createApp().listen(0, "127.0.0.1");
  await new Promise<void>((r) => srv.once("listening", () => r()));
  base = `http://127.0.0.1:${(srv.address() as AddressInfo).port}`;
});
after(async () => {
  srv.close();
  const { redis } = await import("../src/lib/redis"); const { pool } = await import("../src/lib/db");
  await Promise.allSettled([redis.quit(), pool.end()]);
});

describe("real Clerk middleware, fake keys", () => {
  it("no token -> 401 JSON", async () => {
    const r = await fetch(`${base}/api/research/history`);
    assert.equal(r.status, 401);
    assert.equal((await r.json() as { error: string }).error, "unauthorized");
  });
  it("garbage bearer token -> 401 JSON (not 500)", async () => {
    const r = await fetch(`${base}/api/research/history`, { headers: { authorization: "Bearer not.a.jwt" } });
    assert.equal(r.status, 401);
  });
  it("helmet headers present", async () => {
    const r = await fetch(`${base}/api/live`);
    assert.ok(r.headers.get("x-content-type-options") === "nosniff" && r.headers.get("strict-transport-security"));
    assert.equal(r.headers.get("x-powered-by"), null);
  });
});
