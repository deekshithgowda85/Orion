import { confidenceTone, formatPercent, type ConfidenceTone } from "@/lib/format";
import { cn } from "@/lib/utils";

const TONE_STYLES: Record<ConfidenceTone, { bar: string; text: string; badge: string }> = {
  high: {
    bar: "bg-success",
    text: "text-success",
    badge: "border-success/30 bg-success/10 text-success",
  },
  mid: {
    bar: "bg-amber",
    text: "text-amber",
    badge: "border-amber/30 bg-amber/10 text-amber",
  },
  low: {
    bar: "bg-danger",
    text: "text-danger",
    badge: "border-danger/30 bg-danger/10 text-danger",
  },
};

interface ConfidenceBarProps {
  /** 0–1. null/undefined/NaN renders an empty "—" bar instead of a misleading 0%. */
  value: number | null | undefined;
  showLabel?: boolean;
  className?: string;
}

/** Colored progress bar for a 0–1 confidence value (green >0.8, amber 0.6–0.8, red <0.6). */
export function ConfidenceBar({ value, showLabel = true, className }: ConfidenceBarProps) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return (
      <div className={cn("flex items-center gap-2", className)} aria-label="Confidence unavailable">
        <div className="h-1.5 min-w-[56px] flex-1 rounded-full bg-muted" />
        {showLabel && (
          <span className="w-10 text-right font-mono text-xs text-muted-foreground">—</span>
        )}
      </div>
    );
  }
  const clamped = Math.max(0, Math.min(1, value));
  const tone = TONE_STYLES[confidenceTone(clamped)];

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={Number(clamped.toFixed(2))}
        aria-label="Confidence"
        className="h-1.5 min-w-[56px] flex-1 overflow-hidden rounded-full bg-muted"
      >
        <div
          className={cn("h-full rounded-full transition-[width] duration-500", tone.bar)}
          style={{ width: `${clamped * 100}%` }}
        />
      </div>
      {showLabel && (
        <span className={cn("w-10 text-right font-mono text-xs tabular-nums", tone.text)}>
          {formatPercent(clamped)}
        </span>
      )}
    </div>
  );
}

interface ConfidenceBadgeProps {
  score: number | null | undefined;
  className?: string;
}

/** Pill badge: green > 0.8, amber 0.6–0.8, red < 0.6. */
export function ConfidenceBadge({ score, className }: ConfidenceBadgeProps) {
  if (score === null || score === undefined || !Number.isFinite(score)) {
    return (
      <span
        className={cn(
          "inline-flex items-center rounded-full border border-border bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground",
          className,
        )}
      >
        —
      </span>
    );
  }
  const tone = TONE_STYLES[confidenceTone(score)];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-xs tabular-nums",
        tone.badge,
        className,
      )}
    >
      {score.toFixed(2)}
    </span>
  );
}
