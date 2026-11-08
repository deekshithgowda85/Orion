# Layer 5 ⇄ Layer 4 integration contract

Everything the dashboard needs from the BFF (port 3001). The browser only calls `/api/*` on the Next.js origin;
`next.config.ts` rewrites that to `BFF_URL/api/*`. Responses are passed through `lib/normalize.ts`, which tolerates
the aliases listed below and never throws on missing fields — but anything *not* listed will show as empty / "N/A".

## 1. Auth (must match)
| Item | What the frontend does | What Layer 4 must do |
|---|---|---|
| `fetch` calls | Sends `Authorization: Bearer <Clerk session JWT>` **and** the Clerk cookie | Verify the JWT with the Clerk SDK/JWKS (don't hand-parse) |
| **SSE** (`EventSource`) | **Cannot set headers.** Sends cookies only (`withCredentials`, same origin) | **Accept the Clerk `__session` cookie** as an alternative to the Bearer header on `/stream` |
| Tenant | Active Clerk org is inside the token (`org_id`, or `o.id` in v2 tokens). Personal accounts are blocked in the UI | Scope every run/report/history query by that org id; reject tokens with no org |
| Unauthenticated | `/api/*` returns `401 {"error":"Unauthenticated"}` from the Next.js middleware before it reaches the BFF | — |
| Roles | Not used | — |

## 2. Endpoints

### POST `/api/research/submit`
```ts
// request
{ ticker: string;            // "AAPL" — upper-case, /^[A-Z]{1,5}([.-][A-Z]{1,2})?$/
  quarter?: string;          // OPTIONAL, "2025Q3" (omitted entirely when empty)  ← CONFIRM FORMAT
  query: string;             // 10–1000 chars (quick-submit: ≥3)
  workflow_type: "deep_audit" | "daily_scan" | "earnings_pulse";
  priority: "standard" | "high" }
// response (200/201/202)
{ run_id: string; status?: "queued"|"running" }   // aliases accepted: id, runId
```
Non-2xx: body `{detail|message|error: string}` is shown to the user.

### GET `/api/research/{run_id}/status`  (polled every 5 s while queued/running)
```ts
{ run_id: string; ticker: string; query: string;
  workflow_type: WorkflowType;
  status: "queued"|"running"|"completed"|"failed";
  progress_pct: number;            // 0–100
  current_step: string | null;
  conflict_count: number;          // or `conflicts: []` (length used)
  confidence_score: number | null; // 0–1 (0–100 is auto-scaled)
  started_at: string | null; completed_at: string | null;   // ISO-8601
  duration_seconds: number | null;
  error: string | null;            // fatal error (failed runs)
  errors: string[]                 // non-fatal per-source errors; strings or {source,message}
}
```
Status aliases mapped: pending/submitted→queued · in_progress/processing→running · complete/succeeded/success→completed · error/cancelled/timeout→failed.

### GET `/api/research/{run_id}/stream`  (SSE)
Frames are either unnamed `data: {"type": T, "payload": {...}}` **or** named (`event: T` + `data: {...payload}`). Optional `id:` is used for de-duplication on replay. Heartbeat comments (`: ping`) are ignored.
```ts
type T = "run_started" | "progress" | "step_started" | "step_completed" | "conflict_found" | "report_ready" | "run_failed";
run_started    { message?: string }
progress       { progress_pct: number; current_step?: string }
step_started   { step_id?: string; agent: string; label?: string; progress_pct?: number }
step_completed { step_id?: string; agent: string; label?: string; duration_ms?: number; summary?: string; progress_pct?: number }
conflict_found { metric: string; value_a: string|number; source_a: string; value_b: string|number; source_b: string; severity?: string; resolution?: string }
report_ready   { report_id?: string; confidence_score?: number }
run_failed     { error: string }          // alias: message
```
Unknown event types are ignored. **The stream should close after `report_ready` / `run_failed`**; the UI also closes it itself.
On connect the server SHOULD replay events so far (the UI dedupes by `id` / content hash) — otherwise a refresh mid-run shows an empty feed until the next event.

### GET `/api/research/{run_id}/report`  (fetched only once status = completed)
```ts
{ run_id; ticker; quarter?: string|null; generated_at: string;     // alias created_at
  confidence_score: number | null;
  executive_summary: string;                // may contain [1] [2] citation markers → ids of `citations`
  errors: string[];                         // partial-data warnings
  market_snapshot: {…} | null;              // null/missing = "not available" chip. Keys used for fallback metrics: price, market_cap, pe_ratio, fcf_yield
  options_data: {…} | null;
  key_metrics?: { label; value: string|number|null; change_pct?: number|null; source?: string|null }[];
  sections: { id?; title; content }[];      // aliases heading/body/text
  citations: { id: number; source_url; source_type; metric; value: string|number|null; confidence: number|null }[];
  raw_data: Record<string, JSON>;           // alias data
  trace_log: { id?; timestamp; agent; tool; input: JSON; output_summary: string;
               tokens_in: number; tokens_out: number; duration_ms: number; self_correction: string|null }[] }
```
`GET …/report?format=pdf` must return `application/pdf` bytes (Download button; sent with the Bearer header via `fetch`, then saved as a blob).

### GET `/api/research/history`
Query: `page` (1-based), `page_size`, optional `ticker`, `workflow_type`, `status`, `date_from`/`date_to` (`YYYY-MM-DD`), `min_confidence` (0–1), `search`.
```ts
{ items: { run_id; ticker; query; workflow_type; status; confidence_score; conflict_count;
           started_at; completed_at; duration_seconds; executive_summary?: string|null }[];
  total: number; page: number; page_size: number }
```
A bare array, or `runs`/`results`/`data` instead of `items`, is also accepted. **Filtering and pagination must be done server-side** — the UI does not re-filter.
Overview stats, the sidebar "active runs" badge and the workflow canvas all use `page=1&page_size=50` and compute from it (so `status` of in-flight runs must appear there).

## 3. Fields most likely to mismatch
1. **SSE auth** — backend only accepting `Authorization` ⇒ stream 401s and the feed shows "Connection lost" forever.
2. **`run_id` / `id`** in submit response; **`items` vs `runs`** in history; history **missing `total`** (pagination then shows one page).
3. **`progress_pct`** scale (0–100 expected; a fraction 0–1 is auto-detected, but exactly `1` is read as 1 %).
4. **`confidence_score`** scale (0–1 expected; 1–100 auto-scaled) and `null` vs `0`.
5. **Timestamps** — must be ISO-8601 (`2025-11-07T10:00:00Z`); epoch numbers show "—".
6. **`quarter` format** — frontend sends `"2025Q3"`.
7. **Event shape for conflicts** — `value_a/source_a/value_b/source_b` (a `values: []` array is NOT supported).
8. **`errors`** — list of strings or `{source,message}`. If the backend uses another name the "Partial report" banner will not appear.
9. **Citation `id`** must equal the `[n]` used in text, otherwise the hover tooltip has no source.
10. **`workflow_type`** values — snake_case as above; unknown values display as "Deep Audit".
11. Run status after `report_ready` — `/status` must return `completed` (the report query is gated on it).

## 4. Not provided by the backend (client-side only)
* **Scheduled workflows** (Workflows page) are stored in `localStorage`, per browser — there is no schedule endpoint in the contract. They do not run anything and are not org-isolated.
