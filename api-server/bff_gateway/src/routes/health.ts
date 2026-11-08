import { Router } from "express";
import { env } from "../config";
import { pingDb } from "../lib/db";

export const healthRouter = Router();

interface FastApiHealth {
  status?: string;
  neon?: boolean;
  redis?: boolean;
  temporal?: boolean;
}

healthRouter.get("/", async (_req, res) => {
  let fastapi = false;
  let temporal = false;
  let neonViaAgent = false;
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 3000);
    const r = await fetch(`${env.FASTAPI_BASE_URL}/health`, { signal: ctrl.signal });
    clearTimeout(timer);
    fastapi = r.ok || r.status === 503;
    const body = (await r.json()) as FastApiHealth;
    temporal = body.temporal === true;
    neonViaAgent = body.neon === true;
  } catch {
    // leave defaults (all false)
  }
  const neon = neonViaAgent && (await pingDb());
  const ok = fastapi && temporal && neon;
  res.status(ok ? 200 : 503).json({
    status: ok ? "ok" : "degraded",
    services: {
      fastapi: fastapi ? "up" : "down",
      temporal: temporal ? "up" : "down",
      neon: neon ? "up" : "down",
    },
  });
});
