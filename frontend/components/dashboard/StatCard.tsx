"use client";

import type { LucideIcon } from "lucide-react";
import { useCountUp } from "@/hooks/useCountUp";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Accent = "primary" | "cyan" | "amber" | "success";

const ACCENTS: Record<Accent, { icon: string; value: string }> = {
  primary: { icon: "bg-primary/15 text-primary ring-primary/30", value: "text-foreground" },
  cyan: { icon: "bg-primary/10 text-primary ring-primary/25", value: "text-primary" },
  amber: { icon: "bg-amber/10 text-amber ring-amber/30", value: "text-amber" },
  success: { icon: "bg-success/10 text-success ring-success/30", value: "text-success" },
};

interface StatCardProps {
  label: string;
  value: number;
  decimals?: number;
  icon: LucideIcon;
  accent?: Accent;
  hint?: string;
  loading?: boolean;
  /** Shown instead of the number when there is nothing to average, etc. */
  emptyLabel?: string | null;
}

export function StatCard({
  label,
  value,
  decimals = 0,
  icon: Icon,
  accent = "primary",
  hint,
  loading,
  emptyLabel,
}: StatCardProps) {
  const animated = useCountUp(value);
  const styles = ACCENTS[accent];

  return (
    <div className="terminal-card flex items-start justify-between gap-3 p-5">
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </p>
        {loading ? (
          <Skeleton className="mt-2 h-9 w-20" />
        ) : (
          <p
            className={cn(
              "mt-1 font-mono text-3xl font-semibold tabular-nums",
              emptyLabel ? "text-muted-foreground" : styles.value,
            )}
          >
            {emptyLabel ?? animated.toFixed(decimals)}
          </p>
        )}
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      </div>
      <div
        className={cn(
          "flex size-10 shrink-0 items-center justify-center rounded-lg ring-1",
          styles.icon,
        )}
      >
        <Icon className="size-5" />
      </div>
    </div>
  );
}
