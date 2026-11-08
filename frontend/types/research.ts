/* ------------------------------------------------------------------
   Shared domain types for the Orion dashboard.
   ------------------------------------------------------------------ */

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type RunStatusValue = "queued" | "running" | "completed" | "failed";
export type WorkflowType = "deep_audit" | "daily_scan" | "earnings_pulse";
export type Priority = "standard" | "high";

/* ---------------------------- Requests ---------------------------- */

export interface SubmitResearchRequest {
  ticker: string;
  /** Optional fiscal quarter, normalised to "YYYYQn" (e.g. "2025Q3"). Omitted when empty. */
  quarter?: string;
  query: string;
  workflow_type: WorkflowType;
  priority: Priority;
}

export interface SubmitResearchResponse {
  run_id: string;
  status: RunStatusValue;
}

/* ------------------------------ Runs ------------------------------ */

export interface RunStatus {
  run_id: string;
  ticker: string;
  query: string;
  workflow_type: WorkflowType;
  status: RunStatusValue;
  /** 0–100 */
  progress_pct: number;
  current_step: string | null;
  conflict_count: number;
  confidence_score: number | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  error: string | null;
  /** Non-fatal per-source errors reported by the backend (free-tier limits, timeouts…). */
  errors: string[];
}

export interface HistoryItem {
  run_id: string;
  ticker: string;
  query: string;
  workflow_type: WorkflowType;
  status: RunStatusValue;
  confidence_score: number | null;
  conflict_count: number;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  executive_summary?: string | null;
}

export interface ResearchHistoryFilters {
  ticker?: string;
  workflow_type?: WorkflowType | "";
  status?: RunStatusValue | "";
  date_from?: string;
  date_to?: string;
  min_confidence?: number;
  search?: string;
  page: number;
  page_size: number;
}

export interface ResearchHistoryResponse {
  items: HistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

/* ----------------------------- Reports ---------------------------- */

export interface KeyMetric {
  label: string;
  /** Display string; "N/A" when the backend returned null/missing. */
  value: string;
  /** True when the underlying value was null/missing (rendered muted). */
  missing?: boolean;
  change_pct?: number | null;
  source?: string | null;
}

export interface ReportSection {
  id: string;
  title: string;
  /** May contain inline citation markers like [1], [2]. */
  content: string;
}

export interface Citation {
  id: number;
  source_url: string;
  source_type: string;
  metric: string;
  value: string;
  /** 0–1, or null when the backend gave no confidence. */
  confidence: number | null;
}

export interface TraceEntry {
  id: string;
  timestamp: string;
  agent: string;
  tool: string;
  input: JsonValue;
  output_summary: string;
  tokens_in: number;
  tokens_out: number;
  duration_ms: number;
  self_correction: string | null;
}

export interface ResearchReport {
  run_id: string;
  ticker: string;
  generated_at: string;
  confidence_score: number | null;
  executive_summary: string;
  quarter: string | null;
  /** Non-fatal per-source errors (the backend's `errors` list). */
  errors: string[];
  /** null = market snapshot unavailable (free-tier gap). */
  market_snapshot: { [key: string]: JsonValue } | null;
  /** null = options data unavailable. */
  options_data: { [key: string]: JsonValue } | null;
  key_metrics: KeyMetric[];
  sections: ReportSection[];
  citations: Citation[];
  raw_data: { [key: string]: JsonValue };
  trace_log: TraceEntry[];
}

/* ------------------------------ SSE ------------------------------- */

export const SSE_EVENT_TYPES = [
  "run_started",
  "progress",
  "step_started",
  "step_completed",
  "conflict_found",
  "report_ready",
  "run_failed",
] as const;

export type SSEEventType = (typeof SSE_EVENT_TYPES)[number];

export interface RunStartedPayload {
  message: string;
}

export interface ProgressPayload {
  progress_pct: number;
  current_step: string | null;
}

export interface StepStartedPayload {
  step_id: string;
  agent: string;
  label: string;
  progress_pct: number | null;
}

export interface StepCompletedPayload {
  step_id: string;
  agent: string;
  label: string;
  duration_ms: number | null;
  summary: string | null;
  progress_pct: number | null;
}

export interface ConflictFoundPayload {
  metric: string;
  value_a: string;
  source_a: string;
  value_b: string;
  source_b: string;
  severity: string | null;
  resolution: string | null;
}

export interface ReportReadyPayload {
  report_id: string | null;
  confidence_score: number | null;
}

export interface RunFailedPayload {
  error: string;
}

interface BaseAgentEvent {
  /** Stable dedupe key (SSE id, or hash of type + payload). */
  id: string;
  receivedAt: number;
}

export type AgentEvent = BaseAgentEvent &
  (
    | { type: "run_started"; payload: RunStartedPayload }
    | { type: "progress"; payload: ProgressPayload }
    | { type: "step_started"; payload: StepStartedPayload }
    | { type: "step_completed"; payload: StepCompletedPayload }
    | { type: "conflict_found"; payload: ConflictFoundPayload }
    | { type: "report_ready"; payload: ReportReadyPayload }
    | { type: "run_failed"; payload: RunFailedPayload }
  );

export type ConnectionState =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "disconnected"
  | "closed";

/* --------------------------- Schedules ---------------------------- */

export interface ScheduledWorkflow {
  id: string;
  ticker: string;
  workflow_type: WorkflowType;
  cron: string;
  enabled: boolean;
  created_at: string;
}
