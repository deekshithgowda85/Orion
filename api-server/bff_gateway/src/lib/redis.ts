import Redis from "ioredis";
import { env } from "../config";

export const redis = new Redis(env.REDIS_URL, {
  maxRetriesPerRequest: 1,
  
  enableReadyCheck: true,
  lazyConnect: false,
});

redis.on("error", (err: Error) => {
  // eslint-disable-next-line no-console
  console.error(JSON.stringify({ level: "error", msg: "redis error", error: err.message }));
});

/** Bounds every Redis call. ioredis queues commands while disconnected; without this a Redis outage would hang requests. */
export function withRedisTimeout<T>(p: Promise<T>, ms = 800): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`redis timeout after ${ms}ms`)), ms);
    p.then(
      (v) => { clearTimeout(timer); resolve(v); },
      (e: unknown) => { clearTimeout(timer); reject(e instanceof Error ? e : new Error(String(e))); },
    );
  });
}
