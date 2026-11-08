import { format, formatDistanceToNowStrict, isValid, parseISO } from "date-fns";
import type { RunStatusValue } from "@/types/research";

export type ConfidenceTone = "high" | "mid" | "low";

/** green > 0.8, amber 0.6–0.8, red < 0.6 */
export function confidenceTone(score: number): ConfidenceTone {
  if (score > 0.8) return "high";
  if (score >= 0.6) return "mid";
  return "low";
}

export function isTerminalStatus(status: RunStatusValue): boolean {
  return status === "completed" || status === "failed";
}

export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds === null || totalSeconds === undefined || !Number.isFinite(totalSeconds)) {
    return "—";
  }
  const s = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m.toString().padStart(2, "0")}m`;
  if (m > 0) return `${m}m ${sec.toString().padStart(2, "0")}s`;
  return `${sec}s`;
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;
}

export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m.toString().padStart(2, "0")}:${sec.toString().padStart(2, "0")}`;
}

export function safeParseDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = parseISO(value);
  return isValid(d) ? d : null;
}

export function formatDateTime(value: string | null | undefined): string {
  const d = safeParseDate(value);
  return d ? format(d, "MMM d, HH:mm") : "—";
}

export function formatFullDateTime(value: string | null | undefined): string {
  const d = safeParseDate(value);
  return d ? format(d, "MMM d, yyyy · HH:mm:ss") : "—";
}

export function formatRelative(value: string | null | undefined): string {
  const d = safeParseDate(value);
  return d ? `${formatDistanceToNowStrict(d)} ago` : "—";
}

export function formatPercent(score: number | null | undefined, digits = 0): string {
  if (score === null || score === undefined || !Number.isFinite(score)) return "—";
  return `${(score * 100).toFixed(digits)}%`;
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
