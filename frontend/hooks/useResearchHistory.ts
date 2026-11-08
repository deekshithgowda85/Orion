"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { fetchResearchHistory } from "@/lib/api";
import type { ResearchHistoryFilters } from "@/types/research";

interface Options {
  refetchIntervalMs?: number | false;
}

/** Paginated, filterable run history. Previous page stays visible while the next loads. */
export function useResearchHistory(filters: ResearchHistoryFilters, options: Options = {}) {
  return useQuery({
    queryKey: ["research-history", filters],
    queryFn: () => fetchResearchHistory(filters),
    placeholderData: keepPreviousData,
    refetchInterval: options.refetchIntervalMs ?? false,
    staleTime: 10_000,
  });
}
