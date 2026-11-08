/**
 * Demo mode: serves fake /api/research/* data from Next.js route handlers and
 * skips Clerk entirely, so the UI can run before Layers 1–4 (or Clerk keys) exist.
 *
 * Enabled explicitly with NEXT_PUBLIC_MOCK_MODE=true. Production deployments should
 * set it to false and provide a valid Clerk publishable key.
 */
export const MOCK_MODE: boolean =
  process.env.NEXT_PUBLIC_MOCK_MODE === "true";
