import type { Router as ExpressRouter } from "express";
import { Router } from "express";
import { createProxyMiddleware, fixRequestBody } from "http-proxy-middleware";
import type { Request, Response } from "express";
import { env } from "../config";
import { researchSubmitLimiter } from "../middleware/rateLimit";
import { validateBody } from "../middleware/validate";
import { ResearchSubmitSchema, WorkflowScheduleSchema } from "../schemas";

const SSE_TIMEOUT_MS = 36 * 60_000; // FastAPI closes SSE at 35 min

function proxyTo(prefix: "research" | "workflows") {
  return createProxyMiddleware({
    target: env.FASTAPI_BASE_URL,
    changeOrigin: true,
    pathFilter: `/api/${prefix}`,
    pathRewrite: { [`^/api/${prefix}`]: `/${prefix}` },
    proxyTimeout: SSE_TIMEOUT_MS,
    timeout: SSE_TIMEOUT_MS,
    on: {
      // express.json() has already consumed the body; re-serialize it for the upstream request.
      proxyReq: fixRequestBody,
      proxyRes: (proxyRes) => {
        if (String(proxyRes.headers["content-type"] ?? "").startsWith("text/event-stream")) {
          proxyRes.headers["cache-control"] = "no-cache, no-transform";
          proxyRes.headers["x-accel-buffering"] = "no";
        }
      },
      error: (err, _req, res) => {
        const r = res as Response;
        if (!r.headersSent && typeof r.status === "function") {
          r.status(502).json({ error: "bad_gateway", message: "Agent service unavailable", detail: err.message });
        }
      },
    },
  });
}

export function buildProxyRouter(): ExpressRouter {
  const router = Router();

  // Validate (422) and rate-limit before anything reaches the agent service.
  router.post("/api/research/submit", researchSubmitLimiter, validateBody(ResearchSubmitSchema));
  router.post("/api/workflows/schedule", validateBody(WorkflowScheduleSchema));

  router.use(proxyTo("research"));
  router.use(proxyTo("workflows"));
  return router;
}

export type { Request };
