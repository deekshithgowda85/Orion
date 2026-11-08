import { rateLimit, type Options } from "express-rate-limit";
import { RedisStore } from "rate-limit-redis";
import type { Request } from "express";
import { redis, withRedisTimeout } from "../lib/redis";

function store(prefix: string): RedisStore {
  return new RedisStore({
    prefix: `rl:${prefix}:`,
    sendCommand: (command: string, ...args: string[]) =>
      withRedisTimeout(redis.call(command, ...args) as Promise<number | string | (number | string)[]>),
  });
}

const base: Partial<Options> = {
  standardHeaders: "draft-7",
  legacyHeaders: false,
  // If Redis is down, let requests through (fail open) instead of returning 500s.
  passOnStoreError: true,
};

/** 100 requests / minute per user. */
export const perUserLimiter = rateLimit({
  ...base,
  windowMs: 60_000,
  limit: 100,
  store: store("user"),
  keyGenerator: (req: Request) => req.tenant?.userId ?? "anonymous",
  handler: (_req, res) => {
    res.status(429).json({ error: "rate_limited", message: "Too many requests, slow down (100/min per user)" });
  },
});

/** 20 research submissions / hour per tenant. */
export const researchSubmitLimiter = rateLimit({
  ...base,
  windowMs: 60 * 60_000,
  limit: 20,
  store: store("submit"),
  keyGenerator: (req: Request) => req.tenant?.tenantId ?? "anonymous",
  handler: (_req, res) => {
    res.status(429).json({
      error: "rate_limited",
      message: "Research submission limit reached (20/hour per organization)",
    });
  },
});
