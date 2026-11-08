import { env } from "./config";
import { createApp } from "./app";
import { redis } from "./lib/redis";
import { pool } from "./lib/db";

const app = createApp();
const server = app.listen(env.PORT, () => {
  // eslint-disable-next-line no-console
  console.log(JSON.stringify({ level: "info", msg: "bff gateway listening", port: env.PORT }));
});
// Long-lived SSE streams: disable Node's default request/keep-alive timeouts.
server.requestTimeout = 0;
server.keepAliveTimeout = 65_000;

async function shutdown(signal: string): Promise<void> {
  // eslint-disable-next-line no-console
  console.log(JSON.stringify({ level: "info", msg: "shutting down", signal }));
  server.close(async () => {
    await Promise.allSettled([redis.quit(), pool.end()]);
    process.exit(0);
  });
  setTimeout(() => process.exit(1), 10_000).unref();
}

// A Redis outage at boot makes rate-limit-redis's script-load promise reject; log it instead of crashing the gateway.
process.on("unhandledRejection", (reason) => {
  // eslint-disable-next-line no-console
  console.error(JSON.stringify({ level: "error", msg: "unhandled rejection", reason: String(reason) }));
});

process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("SIGINT", () => void shutdown("SIGINT"));
