"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchRunReport } from "@/lib/api";
import type { RunStatusValue } from "@/types/research";

/** Fetches the report only once the run is "completed". */
export function useRunReport(runId: string, status: RunStatusValue | undefined) {
  return useQuery({
    queryKey: ["run-report", runId],
    queryFn: () => fetchRunReport(runId),
    enabled: status === "completed",
    staleTime: 5 * 60_000,
    retry: 2,
  });
}
