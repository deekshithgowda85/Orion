"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRunReport } from "@/hooks/useRunReport";
import type { HistoryItem } from "@/types/research";

/** Inline executive summary for an expanded history row. */
export function ExpandedSummary({ item }: { item: HistoryItem }) {
  const hasInline = typeof item.executive_summary === "string" && item.executive_summary.length > 0;
  // Only hit the report endpoint when the history payload didn't include the summary.
  const report = useRunReport(item.run_id, hasInline ? undefined : item.status);

  let body: React.ReactNode;
  if (hasInline) {
    body = <p className="whitespace-pre-line text-sm leading-relaxed">{item.executive_summary}</p>;
  } else if (item.status !== "completed") {
    body = (
      <p className="text-sm text-muted-foreground">
        {item.status === "failed"
          ? "This run failed before a report was produced."
          : "The summary will be available once the run completes."}
      </p>
    );
  } else if (report.isLoading) {
    body = (
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    );
  } else if (report.isError) {
    body = <p className="text-sm text-danger">Couldn&apos;t load the summary.</p>;
  } else {
    body = (
      <p className="whitespace-pre-line text-sm leading-relaxed">
        {report.data?.executive_summary ?? "No summary available."}
      </p>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        Executive summary
      </p>
      {body}
      <div className="mt-3 flex justify-end">
        <Button asChild size="sm" variant="outline">
          <Link href={`/research/${item.run_id}`}>
            Open full report
            <ArrowUpRight />
          </Link>
        </Button>
      </div>
    </div>
  );
}
