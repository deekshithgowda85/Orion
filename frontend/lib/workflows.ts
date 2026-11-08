import { Gauge, Radar, ScanSearch, type LucideIcon } from "lucide-react";
import type { Priority, WorkflowType } from "@/types/research";

export interface WorkflowOption {
  id: WorkflowType;
  label: string;
  description: string;
  duration: string;
  icon: LucideIcon;
}

export const WORKFLOW_OPTIONS: readonly WorkflowOption[] = [
  {
    id: "deep_audit",
    label: "Deep Audit",
    description:
      "Full multi-agent investigation: filings, market data, news sentiment and quant models with cross-source verification.",
    duration: "~8–12 min",
    icon: ScanSearch,
  },
  {
    id: "daily_scan",
    label: "Daily Scan",
    description:
      "Lightweight sweep of price action, headlines and notable filings since the last close.",
    duration: "~2–3 min",
    icon: Radar,
  },
  {
    id: "earnings_pulse",
    label: "Earnings Pulse",
    description:
      "Focused read on the latest earnings: guidance, surprises, call transcript tone and estimate revisions.",
    duration: "~4–6 min",
    icon: Gauge,
  },
] as const;

export const WORKFLOW_LABELS: Record<WorkflowType, string> = {
  deep_audit: "Deep Audit",
  daily_scan: "Daily Scan",
  earnings_pulse: "Earnings Pulse",
};

export const PRIORITY_LABELS: Record<Priority, string> = {
  standard: "Standard",
  high: "High",
};

export const EXAMPLE_PROMPTS: readonly string[] = [
  "Assess margin sustainability and flag any divergence between reported and consensus figures.",
  "Summarize the latest 10-Q risk-factor changes and their potential impact on guidance.",
  "Compare valuation multiples to sector peers and highlight data conflicts across sources.",
  "What moved the stock this week? Separate news-driven moves from macro-driven ones.",
];

/** Ticker format: 1–5 letters, optional class suffix (BRK.B, RDS-A). */
export const TICKER_PATTERN = /^[A-Z]{1,5}([.-][A-Z]{1,2})?$/;

/**
 * Normalises a fiscal-quarter string to "YYYYQn". Accepts "2025Q3", "Q3 2025", "q3-2025".
 * Returns null when the input isn't a recognisable quarter.
 */
export function normalizeQuarter(input: string): string | null {
  const s = input.trim().toUpperCase().replace(/[\s_-]+/g, "");
  const a = /^(20\d{2})Q([1-4])$/.exec(s);
  if (a) return `${a[1]}Q${a[2]}`;
  const b = /^Q([1-4])(20\d{2})$/.exec(s);
  if (b) return `${b[2]}Q${b[1]}`;
  return null;
}
