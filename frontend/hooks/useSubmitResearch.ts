"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { submitResearch } from "@/lib/api";
import { useResearchStore } from "@/store/research";
import type {
  SubmitResearchRequest,
  SubmitResearchResponse,
  RunStatus,
} from "@/types/research";

type SubmitVars = SubmitResearchRequest;

export function useSubmitResearch() {
  const queryClient = useQueryClient();
  const startTracking = useResearchStore((s) => s.startTracking);

  return useMutation<SubmitResearchResponse, Error, SubmitVars>({
    mutationFn: (vars) => submitResearch(vars),
    onSuccess: (data, vars) => {
      const initial: RunStatus = {
        run_id: data.run_id,
        ticker: vars.ticker,
        query: vars.query,
        workflow_type: vars.workflow_type,
        status: data.status,
        progress_pct: 0,
        current_step: null,
        conflict_count: 0,
        confidence_score: null,
        started_at: new Date().toISOString(),
        completed_at: null,
        duration_seconds: null,
        error: null,
        errors: [],
      };
      startTracking(initial);
      void queryClient.invalidateQueries({ queryKey: ["research-history"] });
    },
  });
}
