import type {
  Citation,
  HistoryItem,
  JsonValue,
  KeyMetric,
  ReportSection,
  ResearchHistoryResponse,
  ResearchReport,
  RunStatus,
  RunStatusValue,
  SubmitResearchResponse,
  TraceEntry,
  WorkflowType,
} from "@/types/research";

/**
 * Boundary validation. Everything the backend returns is `unknown` until it
 * passes through one of these functions, which (a) accept the common alias
 * names, (b) never throw on missing/null fields, and (c) return fully-typed
 * objects so no component ever has to guard against `undefined` or NaN.
 */

type Rec = Record<string, unknown>;

export function isRecord(v: unknown): v is Rec {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function str(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return fallback;
}

function strOrNull(v: unknown): string | null {
  const s = str(v);
  return s.length > 0 ? s : null;
}

function num(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v);
  return null;
}

function firstDefined(rec: Rec, keys: readonly string[]): unknown {
  for (const k of keys) {
    if (rec[k] !== undefined && rec[k] !== null) return rec[k];
  }
  return undefined;
}

/** Deep-converts arbitrary data into JsonValue (undefined → null, depth-capped). */
export function toJson(v: unknown, depth = 0): JsonValue {
  if (depth > 12) return "[max depth]";
  if (v === null || v === undefined) return null;
  if (typeof v === "string" || typeof v === "boolean") return v;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (Array.isArray(v)) return v.map((x) => toJson(x, depth + 1));
  if (isRecord(v)) {
    const out: { [key: string]: JsonValue } = {};
    for (const [k, val] of Object.entries(v)) out[k] = toJson(val, depth + 1);
    return out;
  }
  return String(v);
}

function jsonRecordOrNull(v: unknown): { [key: string]: JsonValue } | null {
  if (!isRecord(v)) return null;
  const j = toJson(v);
  return typeof j === "object" && j !== null && !Array.isArray(j) ? j : null;
}

/** 0–1 score. Accepts 0–100 percentages too. null stays null (never coerced to 0). */
export function toScore(v: unknown): number | null {
  const n = num(v);
  if (n === null) return null;
  const s = n > 1 && n <= 100 ? n / 100 : n;
  return Math.max(0, Math.min(1, s));
}

const WORKFLOWS: readonly WorkflowType[] = ["deep_audit", "daily_scan", "earnings_pulse"];

function toWorkflow(v: unknown): WorkflowType {
  const s = str(v).toLowerCase().replace(/[\s-]+/g, "_");
  return (WORKFLOWS as readonly string[]).includes(s) ? (s as WorkflowType) : "deep_audit";
}

export function toRunStatus(v: unknown): RunStatusValue {
  const s = str(v).toLowerCase();
  if (["queued", "pending", "submitted", "accepted", "created"].includes(s)) return "queued";
  if (["running", "in_progress", "processing", "started", "active"].includes(s)) return "running";
  if (["completed", "complete", "succeeded", "success", "done", "finished"].includes(s)) {
    return "completed";
  }
  if (["failed", "error", "errored", "cancelled", "canceled", "timeout"].includes(s)) return "failed";
  return "queued";
}

/** The backend's `errors` list: strings, or {source, message} objects. */
export function toErrorList(v: unknown): string[] {
  if (!Array.isArray(v)) return typeof v === "string" && v ? [v] : [];
  const out: string[] = [];
  for (const e of v) {
    if (typeof e === "string") {
      if (e) out.push(e);
    } else if (isRecord(e)) {
      const msg = str(firstDefined(e, ["message", "error", "detail", "reason"]));
      const src = str(firstDefined(e, ["source", "agent", "tool", "provider"]));
      if (msg || src) out.push(src && msg ? `${src}: ${msg}` : msg || src);
    }
  }
  return out;
}

/* ------------------------------ submit ------------------------------ */

export function normalizeSubmit(raw: unknown): SubmitResearchResponse | null {
  if (!isRecord(raw)) return null;
  const runId = strOrNull(firstDefined(raw, ["run_id", "runId", "id"]));
  if (!runId) return null;
  return { run_id: runId, status: toRunStatus(raw.status ?? "queued") };
}

/* ------------------------------ status ------------------------------ */

export function normalizeStatus(raw: unknown, fallbackRunId = ""): RunStatus {
  const r = isRecord(raw) ? raw : {};
  const started = strOrNull(firstDefined(r, ["started_at", "created_at", "submitted_at"]));
  const completed = strOrNull(firstDefined(r, ["completed_at", "finished_at", "ended_at"]));
  const conflicts = firstDefined(r, ["conflict_count", "conflicts_count", "conflicts"]);
  let progress = num(firstDefined(r, ["progress_pct", "progress"])) ?? 0;
  if (progress > 0 && progress < 1) progress *= 100; // tolerate a 0–1 fraction
  const status = toRunStatus(r.status);

  return {
    run_id: str(firstDefined(r, ["run_id", "id"]), fallbackRunId),
    ticker: str(r.ticker).toUpperCase(),
    query: str(firstDefined(r, ["query", "prompt"])),
    workflow_type: toWorkflow(firstDefined(r, ["workflow_type", "workflow"])),
    status,
    progress_pct: status === "completed" ? 100 : Math.max(0, Math.min(100, progress)),
    current_step: strOrNull(firstDefined(r, ["current_step", "step", "current_agent"])),
    conflict_count: Array.isArray(conflicts) ? conflicts.length : Math.max(0, num(conflicts) ?? 0),
    confidence_score: toScore(firstDefined(r, ["confidence_score", "confidence"])),
    started_at: started,
    completed_at: completed,
    duration_seconds: num(firstDefined(r, ["duration_seconds", "duration"])),
    error: strOrNull(firstDefined(r, ["error", "error_message"])),
    errors: toErrorList(r.errors),
  };
}

/* ------------------------------ history ----------------------------- */

function normalizeHistoryItem(raw: unknown): HistoryItem | null {
  if (!isRecord(raw)) return null;
  const s = normalizeStatus(raw);
  if (!s.run_id) return null;
  return {
    run_id: s.run_id,
    ticker: s.ticker,
    query: s.query,
    workflow_type: s.workflow_type,
    status: s.status,
    confidence_score: s.confidence_score,
    conflict_count: s.conflict_count,
    started_at: s.started_at ?? "",
    completed_at: s.completed_at,
    duration_seconds: s.duration_seconds,
    executive_summary: strOrNull(firstDefined(raw, ["executive_summary", "summary"])),
  };
}

export function normalizeHistory(
  raw: unknown,
  page: number,
  pageSize: number,
): ResearchHistoryResponse {
  let list: unknown[] = [];
  let total: number | null = null;
  if (Array.isArray(raw)) {
    list = raw;
  } else if (isRecord(raw)) {
    const candidate = firstDefined(raw, ["items", "runs", "results", "data"]);
    if (Array.isArray(candidate)) list = candidate;
    total = num(firstDefined(raw, ["total", "count", "total_count"]));
  }
  const items = list.map(normalizeHistoryItem).filter((x): x is HistoryItem => x !== null);
  return {
    items,
    total: total ?? items.length,
    page: isRecord(raw) ? (num(raw.page) ?? page) : page,
    page_size: isRecord(raw) ? (num(raw.page_size) ?? pageSize) : pageSize,
  };
}

/* ------------------------------ report ------------------------------ */

function formatMetricValue(v: unknown): { text: string; missing: boolean } {
  if (v === null || v === undefined || v === "") return { text: "N/A", missing: true };
  if (typeof v === "number") {
    return Number.isFinite(v)
      ? { text: Math.abs(v) >= 1000 ? v.toLocaleString("en-US") : String(Number(v.toFixed(4))), missing: false }
      : { text: "N/A", missing: true };
  }
  return { text: str(v, "N/A"), missing: false };
}

function normalizeMetrics(raw: unknown, snapshot: Rec | null): KeyMetric[] {
  if (Array.isArray(raw)) {
    const out: KeyMetric[] = [];
    raw.forEach((m, i) => {
      if (!isRecord(m)) return;
      const { text, missing } = formatMetricValue(m.value);
      out.push({
        label: str(firstDefined(m, ["label", "name", "metric"]), `Metric ${i + 1}`),
        value: text,
        missing,
        change_pct: num(firstDefined(m, ["change_pct", "change"])),
        source: strOrNull(m.source),
      });
    });
    return out;
  }
  // No explicit metrics: derive the headline ones from the market snapshot, if there is one.
  if (!snapshot) return [];
  const pick = (label: string, keys: string[]): KeyMetric => {
    const { text, missing } = formatMetricValue(firstDefined(snapshot, keys));
    return { label, value: text, missing };
  };
  return [
    pick("Price", ["price", "last_price", "close"]),
    pick("Market cap", ["market_cap", "marketCap"]),
    pick("P/E", ["pe_ratio", "pe", "trailing_pe"]),
    pick("FCF yield", ["fcf_yield", "free_cash_flow_yield"]),
  ];
}

function normalizeCitations(raw: unknown): Citation[] {
  if (!Array.isArray(raw)) return [];
  const out: Citation[] = [];
  raw.forEach((c, i) => {
    if (!isRecord(c)) return;
    out.push({
      id: num(firstDefined(c, ["id", "index", "n"])) ?? i + 1,
      source_url: str(firstDefined(c, ["source_url", "url"])),
      source_type: str(firstDefined(c, ["source_type", "type"]), "unknown"),
      metric: str(c.metric, "—"),
      value: formatMetricValue(c.value).text,
      confidence: toScore(c.confidence),
    });
  });
  return out;
}

function normalizeSections(raw: unknown): ReportSection[] {
  if (!Array.isArray(raw)) return [];
  const out: ReportSection[] = [];
  raw.forEach((s, i) => {
    if (typeof s === "string") {
      out.push({ id: `s${i}`, title: `Section ${i + 1}`, content: s });
    } else if (isRecord(s)) {
      out.push({
        id: str(s.id, `s${i}`),
        title: str(firstDefined(s, ["title", "heading", "name"]), `Section ${i + 1}`),
        content: str(firstDefined(s, ["content", "body", "text"])),
      });
    }
  });
  return out;
}

function normalizeTrace(raw: unknown): TraceEntry[] {
  if (!Array.isArray(raw)) return [];
  const out: TraceEntry[] = [];
  raw.forEach((t, i) => {
    if (!isRecord(t)) return;
    const output = firstDefined(t, ["output_summary", "output", "result"]);
    out.push({
      id: str(t.id, `t${i}`),
      timestamp: str(firstDefined(t, ["timestamp", "ts", "time"])),
      agent: str(firstDefined(t, ["agent", "agent_name"]), "agent"),
      tool: str(firstDefined(t, ["tool", "tool_name", "name"]), "unknown"),
      input: toJson(firstDefined(t, ["input", "args", "arguments"]) ?? null),
      output_summary: typeof output === "string" ? output : output === undefined ? "" : JSON.stringify(toJson(output)),
      tokens_in: num(firstDefined(t, ["tokens_in", "input_tokens", "prompt_tokens"])) ?? 0,
      tokens_out: num(firstDefined(t, ["tokens_out", "output_tokens", "completion_tokens"])) ?? 0,
      duration_ms: num(firstDefined(t, ["duration_ms", "latency_ms"])) ?? 0,
      self_correction: strOrNull(firstDefined(t, ["self_correction", "correction"])),
    });
  });
  return out;
}

export function normalizeReport(raw: unknown, fallbackRunId = ""): ResearchReport {
  const r = isRecord(raw) ? raw : {};
  const rawData = jsonRecordOrNull(firstDefined(r, ["raw_data", "data"])) ?? {};
  const snapshotSrc = firstDefined(r, ["market_snapshot", "snapshot"]) ?? rawData.market_snapshot;
  const optionsSrc = firstDefined(r, ["options_data", "options"]) ?? rawData.options_data;
  const snapshot = jsonRecordOrNull(snapshotSrc);

  return {
    run_id: str(r.run_id, fallbackRunId),
    ticker: str(r.ticker).toUpperCase(),
    generated_at: str(firstDefined(r, ["generated_at", "created_at", "completed_at"])),
    confidence_score: toScore(firstDefined(r, ["confidence_score", "confidence"])),
    executive_summary: str(firstDefined(r, ["executive_summary", "summary"])),
    quarter: strOrNull(r.quarter),
    errors: toErrorList(r.errors),
    market_snapshot: snapshot,
    options_data: jsonRecordOrNull(optionsSrc),
    key_metrics: normalizeMetrics(firstDefined(r, ["key_metrics", "metrics"]), snapshot),
    sections: normalizeSections(r.sections),
    citations: normalizeCitations(r.citations),
    raw_data: rawData,
    trace_log: normalizeTrace(firstDefined(r, ["trace_log", "trace"])),
  };
}
