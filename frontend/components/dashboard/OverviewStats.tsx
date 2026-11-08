"use client";

import { useMemo } from "react";
import { isToday } from "date-fns";
import { Activity, AlertTriangle, Gauge, ListChecks } from "lucide-react";
import { StatCard } from "@/components/dashboard/StatCard";
import { useResearchHistory } from "@/hooks/useResearchHistory";
import { safeParseDate } from "@/lib/format";

export function OverviewStats() {
  const { data, isLoading } = useResearchHistory(
    { page: 1, page_size: 50 },
    { refetchIntervalMs: 10_000 },
  );

  const stats = useMemo(() => {
    const items = data?.items ?? [];
    const today = items.filter((i) => {
      const d = safeParseDate(i.started_at);
      return d !== null && isToday(d);
    });

    const active = items.filter((i) => i.status === "running" || i.status === "queued").length;

    const scored = today.filter((i) => i.status === "completed" && i.confidence_score !== null);
    const avgConfidence =
      scored.length > 0
        ? scored.reduce((sum, i) => sum + (i.confidence_score ?? 0), 0) / scored.length
        : null;

    const conflicts = today.reduce((sum, i) => sum + i.conflict_count, 0);

    return { totalToday: today.length, active, avgConfidence, conflicts };
  }, [data]);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        label="Total Runs Today"
        value={stats.totalToday}
        icon={ListChecks}
        accent="primary"
        loading={isLoading}
        hint="Started since midnight"
      />
      <StatCard
        label="Active Runs"
        value={stats.active}
        icon={Activity}
        accent="cyan"
        loading={isLoading}
        hint="Queued or running now"
      />
      <StatCard
        label="Avg Confidence"
        value={stats.avgConfidence ?? 0}
        decimals={2}
        icon={Gauge}
        accent="success"
        loading={isLoading}
        emptyLabel={stats.avgConfidence === null ? "—" : null}
        hint="Completed runs today"
      />
      <StatCard
        label="Conflicts Flagged"
        value={stats.conflicts}
        icon={AlertTriangle}
        accent="amber"
        loading={isLoading}
        hint="Cross-source data conflicts today"
      />
    </div>
  );
}
