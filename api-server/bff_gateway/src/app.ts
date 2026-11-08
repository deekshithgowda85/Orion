import { randomUUID } from "node:crypto";
import cors from "cors";
import express, { type NextFunction, type Request, type RequestHandler, type Response } from "express";
import helmet from "helmet";
import { clerkMiddleware } from "@clerk/express";
import { env } from "./config";
import { requireApiAuth } from "./middleware/auth";
import { perUserLimiter } from "./middleware/rateLimit";
import { tenantMiddleware } from "./middleware/tenant";
import { healthRouter } from "./routes/health";
import { buildProxyRouter } from "./routes/proxy";
import { userRouter } from "./routes/user";

export interface AppOptions {
  /** Replaces the Clerk auth + tenant stack (used by tests). Must set req.tenant and the x-tenant-id / x-user-id headers. */
  authStack?: RequestHandler[];
}

/** Clerk throws on malformed tokens (-> would be a 500). Any failure inside Clerk's verification is a 401. */
function safeClerk(): RequestHandler {
  const clerk = clerkMiddleware({ secretKey: env.CLERK_SECRET_KEY, publishableKey: env.CLERK_PUBLISHABLE_KEY });
  return (req, res, next) => {
    try {
      void clerk(req, res, (err?: unknown) => {
        if (err) {
          // eslint-disable-next-line no-console
          console.warn(JSON.stringify({ level: "warn", msg: "clerk rejected request", error: String(err), request_id: req.requestId }));
          res.status(401).json({ error: "unauthorized", message: "Invalid or malformed authentication token" });
          return;
        }
        next();
      });
    } catch (err) {
      res.status(401).json({ error: "unauthorized", message: "Invalid or malformed authentication token", detail: String(err) });
    }
  };
}

function defaultAuthStack(): RequestHandler[] {
  return [
    safeClerk(),
    requireApiAuth,
    tenantMiddleware,
  ];
}

export function createApp(options: AppOptions = {}): express.Express {
  const app = express();
  app.set("trust proxy", 1);
  app.disable("x-powered-by");

  app.use(helmet());
  app.use(
    cors({
      origin: env.allowedOrigins,
      credentials: true,
      methods: ["GET", "POST", "DELETE", "OPTIONS"],
      allowedHeaders: ["Authorization", "Content-Type", "X-Request-ID"],
      exposedHeaders: ["X-Request-ID"],
    }),
  );

  // Request ID + JSON access log
  app.use((req: Request, res: Response, next: NextFunction) => {
    const id = (req.headers["x-request-id"] as string | undefined) ?? randomUUID();
    req.requestId = id;
    req.headers["x-request-id"] = id;
    res.setHeader("X-Request-ID", id);
    const start = process.hrtime.bigint();
    res.on("finish", () => {
      const ms = Number(process.hrtime.bigint() - start) / 1e6;
      // eslint-disable-next-line no-console
      console.log(
        JSON.stringify({
          level: "info",
          msg: "request",
          request_id: id,
          method: req.method,
          path: req.originalUrl.split("?")[0],
          status: res.statusCode,
          duration_ms: Math.round(ms * 100) / 100,
          tenant_id: req.tenant?.tenantId ?? null,
          user_id: req.tenant?.userId ?? null,
        }),
      );
    });
    next();
  });

  // Public endpoints: liveness (no dependencies) and dependency health.
  app.get("/api/live", (_req, res) => {
    res.json({ status: "ok" });
  });
  app.use("/api/health", healthRouter);

  app.use(express.json({ limit: "100kb" }));

  // Everything below requires auth + a resolved tenant.
  app.use("/api", ...(options.authStack ?? defaultAuthStack()), perUserLimiter);
  app.use("/api/user", userRouter);
  app.use(buildProxyRouter());

  app.use((_req: Request, res: Response) => {
    res.status(404).json({ error: "not_found", message: "Route not found" });
  });

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  app.use((err: Error & { status?: number; type?: string; code?: string }, req: Request, res: Response, _next: NextFunction) => {
    if (res.headersSent) return;
    if (err.type === "entity.parse.failed") {
      res.status(400).json({ error: "bad_json", message: "Request body is not valid JSON" });
      return;
    }
    if (err.type === "entity.too.large") {
      res.status(413).json({ error: "payload_too_large", message: "Request body too large" });
      return;
    }
    // eslint-disable-next-line no-console
    console.error(JSON.stringify({ level: "error", msg: err.message, code: err.code, request_id: req.requestId }));
    const dbDown = ["ECONNREFUSED", "ETIMEDOUT", "ENOTFOUND", "57P03", "08006", "08001"].includes(err.code ?? "");
    if (dbDown) {
      res.status(503).json({ error: "dependency_unavailable", message: "Database temporarily unavailable", request_id: req.requestId });
      return;
    }
    res.status(500).json({ error: "internal_error", message: "Internal server error", request_id: req.requestId });
  });

  return app;
}
