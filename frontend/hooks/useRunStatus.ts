"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRunStatus } from "@/lib/api";
import { useResearchStore } from "@/store/research";

/**
 * Polls the status endpoint every 5s while the run is queued/running, and
 * merges each snapshot into the Zustand store (without regressing live SSE state).
 * Pass `null` to stay idle.
 */
export function useRunStatus(runId: string | null) {
  const syncRunStatus = useResearchStore((s) => s.syncRunStatus);

  const query = useQuery({
    queryKey: ["run-status", runId],
    queryFn: () => fetchRunStatus(runId as string),
    enabled: runId !== null,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status === "running" || status === "queued" ? 5000 : false;
    },
    retry: 1,
  });

  useEffect(() => {
    if (query.data) syncRunStatus(query.data);
  }, [query.data, syncRunStatus]);

  return query;
}
