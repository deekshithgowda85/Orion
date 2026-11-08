import { TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string;
  /** Percent change, e.g. 3.2 or -1.4 */
  changePct?: number | null;
  source?: string | null;
  /** Value was null/missing in the backend response — render muted. */
  missing?: boolean;
  className?: string;
}

/** Financial metric tile: label, mono value, change %, source. */
export function MetricCard({ label, value, changePct, source, missing, className }: MetricCardProps) {
  const hasChange = typeof changePct === "number" && Number.isFinite(changePct);
  const positive = hasChange && (changePct as number) >= 0;

  return (
    <div className={cn("terminal-card flex flex-col gap-2 p-4", className)}>
      <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <div className="flex items-end justify-between gap-2">
        <p
          className={cn(
            "font-mono text-2xl font-semibold tabular-nums",
            missing ? "text-muted-foreground/60" : "text-foreground",
          )}
          title={missing ? "Not available from the data providers for this run" : undefined}
        >
          {value}
        </p>
        {hasChange && (
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-xs tabular-nums",
              positive ? "bg-success/10 text-success" : "bg-danger/10 text-danger",
            )}
          >
            {positive ? <TrendingUp className="size-3" /> : <TrendingDown className="size-3" />}
            {positive ? "+" : ""}
            {(changePct as number).toFixed(2)}%
          </span>
        )}
      </div>
      {source && (
        <p className="truncate font-mono text-[11px] text-muted-foreground/80" title={source}>
          src: {source}
        </p>
      )}
    </div>
  );
}
