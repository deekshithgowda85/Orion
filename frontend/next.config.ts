import type { NextConfig } from "next";

/**
 * All browser traffic goes to /api/* on this Next.js origin and is proxied to
 * the BFF gateway (port 3001 by default). The browser never talks to the
 * backend (port 8000) directly.
 *
 * BFF_URL is read on the server only (no NEXT_PUBLIC_ prefix) — it is never sent to the browser.
 */
const BFF_URL = (process.env.BFF_URL ?? "http://localhost:3001").replace(/\/$/, "");

// Demo mode (dev only): /api/research/* is answered by app/api/** mock route handlers.
const MOCK_MODE =
  process.env.NEXT_PUBLIC_MOCK_MODE === "true" && process.env.NODE_ENV !== "production";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // gzip buffering breaks Server-Sent Events through the proxy.
  compress: false,
  async rewrites() {
    // `beforeFiles` makes the proxy win over the mock route handlers in app/api,
    // so the mocks can only ever answer when MOCK_MODE is on.
    return {
      beforeFiles: MOCK_MODE
        ? []
        : [{ source: "/api/:path*", destination: `${BFF_URL}/api/:path*` }],
      afterFiles: [],
      fallback: [],
    };
  },
  async headers() {
    return [
      {
        source: "/api/research/:run_id/stream",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-transform" },
          { key: "X-Accel-Buffering", value: "no" },
          { key: "Connection", value: "keep-alive" },
        ],
      },
    ];
  },
};

export default nextConfig;
