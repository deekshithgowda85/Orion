# Layer 5 — Orion Dashboard

Next.js 15 (App Router) · Clerk · React Flow · Tailwind v4 · Zustand · TanStack Query · Recharts

## Windows quick start (PowerShell)
    node -v                          # needs Node 18.18+ (20 or 22 recommended)
    npm install
    Copy-Item .env.local.example .env.local   # then edit: Clerk keys + BFF_URL
    npm run dev                      # http://localhost:3000
    npm run build ; npm run start    # production

## See it WITHOUT the backend or Clerk keys
    npm run dev:mock                 # http://localhost:3000 — fake API + no login
Special tickers in demo mode: `THIN` (missing market/options data + errors list), `FAIL` (run fails),
`LONG` (huge report), anything else = healthy ~22 s run. Demo mode is dev-only and ignored in production builds.

## Scripts
`dev` · `dev:mock` · `build` · `start` · `lint` (eslint) · `typecheck` (tsc --noEmit)

## Docs
`LAYER5_INTEGRATION.md` — exact request/response/auth contract Layer 4 must satisfy.
