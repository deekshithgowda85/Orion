"use client";

import { useMemo } from "react";
import { useResearchHistory } from "@/hooks/useResearchHistory";
import { useResearchStore } from "@/store/research";
import type { RunStatus } from "@/types/research";

/** Number of queued/running runs (server history merged with locally tracked runs). */
export function useActiveRunCount(): number {
  const { data } = useResearchHistory(
    { page: 1, page_size: 50 },
    { refetchIntervalMs: 10_000 },
  );
  const tracked = useResearchStore((s) => s.activeRuns);

  return useMemo(() => {
    const ids = new Set<string>();
    data?.items.forEach((item) => {
      if (item.status === "running" || item.status === "queued") ids.add(item.run_id);
    });
    tracked.forEach((run: RunStatus, id: string) => {
      // Placeholder entries (no ticker yet) are created by the live run page
      // before the first status snapshot arrives — don't count those as active.
      if (run.ticker && (run.status === "running" || run.status === "queued")) ids.add(id);
      else if (run.status === "completed" || run.status === "failed") ids.delete(id);
    });
    return ids.size;
  }, [data, tracked]);
}
