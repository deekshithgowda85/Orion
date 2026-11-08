import type {
  ResearchHistoryFilters,
  ResearchHistoryResponse,
  ResearchReport,
  RunStatus,
  SubmitResearchRequest,
  SubmitResearchResponse,
} from "@/types/research";
import { normalizeHistory, normalizeReport, normalizeStatus, normalizeSubmit } from "@/lib/normalize";

/**
 * Every call goes to the same-origin /api/* proxy (see next.config.ts), which
 * forwards to the BFF gateway. Nothing here ever targets the backend directly.
 */

type TokenGetter = () => Promise<string | null>;

let tokenGetter: TokenGetter | null = null;

/** Registered once by <AuthTokenBridge/> so fetches carry the Clerk session JWT. */
export function setAuthTokenGetter(getter: TokenGetter | null): void {
  tokenGetter = getter;
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function buildHeaders(extra?: HeadersInit, json = false): Promise<Headers> {
  const headers = new Headers(extra);
  if (json && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (tokenGetter) {
    const token = await tokenGetter();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  let message = `Request failed (${res.status})`;
  try {
    const text = await res.text();
    if (text) {
      try {
        body = JSON.parse(text) as unknown;
        if (typeof body === "object" && body !== null) {
          const rec = body as Record<string, unknown>;
          const detail = rec.detail ?? rec.message ?? rec.error;
          if (typeof detail === "string") message = detail;
        }
      } catch {
        body = text;
        message = text.slice(0, 200);
      }
    }
  } catch {
    /* ignore body read errors */
  }
  return new ApiError(res.status, message, body);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = await buildHeaders(init.headers, init.body !== undefined);
  const res = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

/* ------------------------------------------------------------------ */

export async function submitResearch(body: SubmitResearchRequest): Promise<SubmitResearchResponse> {
  const raw = await apiFetch<unknown>("/api/research/submit", {
    method: "POST",
    body: JSON.stringify(body),
  });
  const parsed = normalizeSubmit(raw);
  if (!parsed) throw new ApiError(502, "The server accepted the request but returned no run_id.", raw);
  return parsed;
}

export async function fetchRunStatus(runId: string): Promise<RunStatus> {
  const raw = await apiFetch<unknown>(`/api/research/${encodeURIComponent(runId)}/status`);
  return normalizeStatus(raw, runId);
}

export async function fetchRunReport(runId: string): Promise<ResearchReport> {
  const raw = await apiFetch<unknown>(`/api/research/${encodeURIComponent(runId)}/report`);
  return normalizeReport(raw, runId);
}

export async function fetchResearchHistory(
  filters: ResearchHistoryFilters,
): Promise<ResearchHistoryResponse> {
  const params = new URLSearchParams();
  params.set("page", String(filters.page));
  params.set("page_size", String(filters.page_size));
  if (filters.ticker) params.set("ticker", filters.ticker);
  if (filters.workflow_type) params.set("workflow_type", filters.workflow_type);
  if (filters.status) params.set("status", filters.status);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  if (filters.search) params.set("search", filters.search);
  if (filters.min_confidence !== undefined && filters.min_confidence > 0) {
    params.set("min_confidence", String(filters.min_confidence));
  }
  const raw = await apiFetch<unknown>(`/api/research/history?${params.toString()}`);
  return normalizeHistory(raw, filters.page, filters.page_size);
}

/** Downloads the PDF report as a file in the browser. */
export async function downloadReportPdf(runId: string, ticker: string): Promise<void> {
  const headers = await buildHeaders({ Accept: "application/pdf" });
  const res = await fetch(`/api/research/${encodeURIComponent(runId)}/report?format=pdf`, {
    headers,
    credentials: "same-origin",
  });
  if (!res.ok) throw await toApiError(res);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${ticker}-${runId.slice(0, 8)}-report.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
