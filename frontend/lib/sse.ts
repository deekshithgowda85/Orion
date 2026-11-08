import {
  SSE_EVENT_TYPES,
  type AgentEvent,
  type SSEEventType,
} from "@/types/research";

/**
 * Safe parsing of SSE frames into typed AgentEvents. The backend streams
 * `{type, payload}` objects; we also accept bare payloads when the server uses
 * named SSE events (`event: step_started`). Nothing here uses `any`.
 */

type UnknownRecord = Record<string, unknown>;

function isRecord(v: unknown): v is UnknownRecord {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function isEventType(v: unknown): v is SSEEventType {
  return typeof v === "string" && (SSE_EVENT_TYPES as readonly string[]).includes(v);
}

function str(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return fallback;
}

function strOrNull(v: unknown): string | null {
  if (typeof v === "string" && v.length > 0) return v;
  if (typeof v === "number") return String(v);
  return null;
}

function numOrNull(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v);
  return null;
}

function clampPct(v: number | null): number | null {
  if (v === null) return null;
  return Math.max(0, Math.min(100, v));
}

/** Human-friendly label from an agent identifier, e.g. "market_data" → "Market Data". */
export function prettyAgentName(name: string): string {
  return name
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function hashString(input: string): string {
  let h = 5381;
  for (let i = 0; i < input.length; i += 1) {
    h = ((h << 5) + h + input.charCodeAt(i)) | 0;
  }
  return (h >>> 0).toString(36);
}

export interface ParsedFrame {
  type: SSEEventType;
  payload: UnknownRecord;
}

/** Parses raw `data:` text. Returns null for heartbeats / unknown / malformed frames. */
export function parseSSEData(raw: string, fallbackType?: SSEEventType): ParsedFrame | null {
  let data: unknown;
  try {
    data = JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
  if (!isRecord(data)) return null;

  if (isEventType(data.type)) {
    const payload = isRecord(data.payload) ? data.payload : {};
    return { type: data.type, payload };
  }
  if (fallbackType) return { type: fallbackType, payload: data };
  return null;
}

/** Builds a strongly typed AgentEvent from a parsed frame. */
export function buildAgentEvent(frame: ParsedFrame, lastEventId: string): AgentEvent {
  const { type, payload } = frame;
  const id = lastEventId
    ? `sse:${lastEventId}`
    : `h:${type}:${hashString(JSON.stringify(payload))}`;
  const receivedAt = Date.now();

  switch (type) {
    case "run_started":
      return {
        id,
        receivedAt,
        type,
        payload: { message: str(payload.message, "Run started") },
      };
    case "progress":
      return {
        id,
        receivedAt,
        type,
        payload: {
          progress_pct: clampPct(numOrNull(payload.progress_pct)) ?? 0,
          current_step: strOrNull(payload.current_step ?? payload.step),
        },
      };
    case "step_started": {
      const agent = str(payload.agent ?? payload.agent_name, "agent");
      return {
        id,
        receivedAt,
        type,
        payload: {
          step_id: str(payload.step_id ?? payload.id, agent),
          agent,
          label: str(payload.label ?? payload.step ?? payload.description, prettyAgentName(agent)),
          progress_pct: clampPct(numOrNull(payload.progress_pct)),
        },
      };
    }
    case "step_completed": {
      const agent = str(payload.agent ?? payload.agent_name, "agent");
      const durationMs =
        numOrNull(payload.duration_ms) ??
        (numOrNull(payload.duration_seconds) !== null
          ? (numOrNull(payload.duration_seconds) as number) * 1000
          : null);
      return {
        id,
        receivedAt,
        type,
        payload: {
          step_id: str(payload.step_id ?? payload.id, agent),
          agent,
          label: str(payload.label ?? payload.step ?? payload.description, prettyAgentName(agent)),
          duration_ms: durationMs,
          summary: strOrNull(payload.summary),
          progress_pct: clampPct(numOrNull(payload.progress_pct)),
        },
      };
    }
    case "conflict_found":
      return {
        id,
        receivedAt,
        type,
        payload: {
          metric: str(payload.metric, "Unknown metric"),
          value_a: str(payload.value_a ?? payload.first_value),
          source_a: str(payload.source_a ?? payload.first_source, "source A"),
          value_b: str(payload.value_b ?? payload.second_value),
          source_b: str(payload.source_b ?? payload.second_source, "source B"),
          severity: strOrNull(payload.severity),
          resolution: strOrNull(payload.resolution),
        },
      };
    case "report_ready":
      return {
        id,
        receivedAt,
        type,
        payload: {
          report_id: strOrNull(payload.report_id),
          confidence_score: numOrNull(payload.confidence_score),
        },
      };
    case "run_failed":
      return {
        id,
        receivedAt,
        type,
        payload: { error: str(payload.error ?? payload.message, "Run failed") },
      };
  }
}
