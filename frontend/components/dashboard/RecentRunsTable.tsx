"use client";

import Link from "next/link";
import { ArrowUpRight, Inbox } from "lucide-react";
import { ConfidenceBadge } from "@/components/ConfidenceBar";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useResearchHistory } from "@/hooks/useResearchHistory";
import { formatDuration, formatFullDateTime, formatRelative } from "@/lib/format";
import { WORKFLOW_LABELS } from "@/lib/workflows";

const ROWS = 8;

export function RecentRunsTable() {
  const { data, isLoading, isError, error } = useResearchHistory(
    { page: 1, page_size: 50 },
    { refetchIntervalMs: 10_000 },
  );
  const items = (data?.items ?? []).slice(0, ROWS);

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between">
        <div>
          <CardTitle>Recent runs</CardTitle>
          <CardDescription>Latest research workflows across your organization.</CardDescription>
        </div>
        <Button asChild variant="ghost" size="sm">
          <Link href="/reports">
            All reports
            <ArrowUpRight />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="px-2 pb-3">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Ticker</TableHead>
              <TableHead>Query</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Started</TableHead>
              <TableHead className="text-right">Duration</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i} className="hover:bg-transparent">
                  {Array.from({ length: 7 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading &&
              items.map((run) => (
                <TableRow key={run.run_id}>
                  <TableCell>
                    <div className="font-mono text-sm font-semibold text-primary">{run.ticker}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {WORKFLOW_LABELS[run.workflow_type]}
                    </div>
                  </TableCell>
                  <TableCell className="max-w-[280px]">
                    <p className="truncate text-muted-foreground" title={run.query}>
                      {run.query}
                    </p>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={run.status} />
                  </TableCell>
                  <TableCell>
                    <ConfidenceBadge score={run.confidence_score} />
                  </TableCell>
                  <TableCell>
                    <span
                      className="whitespace-nowrap text-xs text-muted-foreground"
                      title={formatFullDateTime(run.started_at)}
                    >
                      {formatRelative(run.started_at)}
                    </span>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums">
                    {formatDuration(run.duration_seconds)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button asChild variant="outline" size="sm">
                      <Link href={`/research/${run.run_id}`}>
                        {run.status === "running" || run.status === "queued" ? "Watch" : "Open"}
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>

        {isError && (
          <p className="px-3 py-8 text-center text-sm text-danger">
            Couldn&apos;t load runs{error instanceof Error ? `: ${error.message}` : "."}
          </p>
        )}

        {!isLoading && !isError && items.length === 0 && (
          <div className="flex flex-col items-center gap-2 px-3 py-10 text-center">
            <Inbox className="size-8 text-muted-foreground/60" />
            <p className="text-sm text-muted-foreground">No runs yet — launch your first one above.</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
