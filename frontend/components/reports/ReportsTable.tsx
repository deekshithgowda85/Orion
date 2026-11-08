"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Download, FileSearch, Loader2, Search } from "lucide-react";
import { ConfidenceBadge } from "@/components/ConfidenceBar";
import { ExpandedSummary } from "@/components/reports/ExpandedSummary";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useResearchHistory } from "@/hooks/useResearchHistory";
import { downloadReportPdf } from "@/lib/api";
import { formatDateTime, formatDuration } from "@/lib/format";
import { WORKFLOW_LABELS, WORKFLOW_OPTIONS } from "@/lib/workflows";
import { cn } from "@/lib/utils";
import type { ResearchHistoryFilters, WorkflowType } from "@/types/research";

const PAGE_SIZE = 15;

export function ReportsTable() {
  const [tickerText, setTickerText] = useState("");
  const [searchText, setSearchText] = useState("");
  const [workflow, setWorkflow] = useState<WorkflowType | "">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [minConfidence, setMinConfidence] = useState(0);
  const [page, setPage] = useState(1);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const ticker = useDebouncedValue(tickerText.trim().toUpperCase(), 300);
  const search = useDebouncedValue(searchText.trim(), 300);
  const confidence = useDebouncedValue(minConfidence, 300);

  // Any filter change returns to the first page.
  useEffect(() => {
    setPage(1);
  }, [ticker, search, workflow, dateFrom, dateTo, confidence]);

  const filters = useMemo<ResearchHistoryFilters>(
    () => ({
      page,
      page_size: PAGE_SIZE,
      ticker: ticker || undefined,
      search: search || undefined,
      workflow_type: workflow,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      min_confidence: confidence,
    }),
    [page, ticker, search, workflow, dateFrom, dateTo, confidence],
  );

  const { data, isLoading, isError, error, isFetching } = useResearchHistory(filters, {
    refetchIntervalMs: 15_000,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const firstShown = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const lastShown = Math.min(page * PAGE_SIZE, total);

  const hasFilters =
    ticker !== "" || search !== "" || workflow !== "" || dateFrom !== "" || dateTo !== "" || confidence > 0;

  const resetFilters = () => {
    setTickerText("");
    setSearchText("");
    setWorkflow("");
    setDateFrom("");
    setDateTo("");
    setMinConfidence(0);
  };

  const download = async (runId: string, runTicker: string) => {
    setDownloadingId(runId);
    setDownloadError(null);
    try {
      await downloadReportPdf(runId, runTicker);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div className="space-y-5">
      {/* Filters */}
      <Card>
        <CardContent className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-6">
          <div className="space-y-1.5">
            <Label htmlFor="f-ticker">Ticker</Label>
            <Input
              id="f-ticker"
              value={tickerText}
              onChange={(e) => setTickerText(e.target.value.toUpperCase())}
              placeholder="AAPL"
              className="font-mono uppercase"
            />
          </div>
          <div className="space-y-1.5 lg:col-span-2">
            <Label htmlFor="f-search">Search queries</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="f-search"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="margin, guidance, risk factors…"
                className="pl-9"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="f-workflow">Workflow</Label>
            <select
              id="f-workflow"
              value={workflow}
              onChange={(e) => setWorkflow(e.target.value as WorkflowType | "")}
              className="flex h-9 w-full rounded-md border border-border bg-input px-3 text-sm focus-visible:border-primary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
            >
              <option value="">All workflows</option>
              {WORKFLOW_OPTIONS.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="f-from">From</Label>
            <Input
              id="f-from"
              type="date"
              value={dateFrom}
              max={dateTo || undefined}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="f-to">To</Label>
            <Input
              id="f-to"
              type="date"
              value={dateTo}
              min={dateFrom || undefined}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2 lg:col-span-4">
            <div className="flex items-center justify-between">
              <Label htmlFor="f-conf">Min confidence</Label>
              <span className="font-mono text-xs text-primary">{minConfidence.toFixed(2)}</span>
            </div>
            <input
              id="f-conf"
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={minConfidence}
              onChange={(e) => setMinConfidence(Number(e.target.value))}
              className="h-2 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary"
            />
          </div>
          <div className="flex items-end justify-end sm:col-span-2">
            <Button variant="ghost" size="sm" onClick={resetFilters} disabled={!hasFilters}>
              Reset filters
            </Button>
          </div>
        </CardContent>
      </Card>

      {downloadError && (
        <p
          role="alert"
          className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger"
        >
          {downloadError}
        </p>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-2">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-10" />
                <TableHead>Ticker</TableHead>
                <TableHead>Workflow</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Started</TableHead>
                <TableHead className="text-right">Duration</TableHead>
                <TableHead className="text-right">Report</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i} className="hover:bg-transparent">
                    {Array.from({ length: 8 }).map((__, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}

              {!isLoading &&
                items.map((item) => {
                  const expanded = expandedId === item.run_id;
                  return (
                    <Fragment key={item.run_id}>
                      <TableRow className={cn(expanded && "bg-muted/30")}>
                        <TableCell className="pr-0">
                          <button
                            type="button"
                            onClick={() => setExpandedId(expanded ? null : item.run_id)}
                            aria-expanded={expanded}
                            aria-label={expanded ? "Collapse summary" : "Expand summary"}
                            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                          >
                            <ChevronRight
                              className={cn("size-4 transition-transform", expanded && "rotate-90")}
                            />
                          </button>
                        </TableCell>
                        <TableCell>
                          <p className="font-mono text-sm font-semibold text-primary">{item.ticker}</p>
                          <p
                            className="max-w-[240px] truncate text-[11px] text-muted-foreground"
                            title={item.query}
                          >
                            {item.query}
                          </p>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {WORKFLOW_LABELS[item.workflow_type]}
                        </TableCell>
                        <TableCell>
                          <StatusBadge status={item.status} />
                        </TableCell>
                        <TableCell>
                          <ConfidenceBadge score={item.confidence_score} />
                        </TableCell>
                        <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                          {formatDateTime(item.started_at)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {formatDuration(item.duration_seconds)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={item.status !== "completed" || downloadingId === item.run_id}
                            onClick={() => void download(item.run_id, item.ticker)}
                            aria-label={`Download PDF report for ${item.ticker}`}
                          >
                            {downloadingId === item.run_id ? (
                              <Loader2 className="animate-spin" />
                            ) : (
                              <Download />
                            )}
                            PDF
                          </Button>
                        </TableCell>
                      </TableRow>
                      {expanded && (
                        <TableRow className="hover:bg-transparent">
                          <TableCell colSpan={8} className="px-4 pb-4 pt-1">
                            <ExpandedSummary item={item} />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
            </TableBody>
          </Table>

          {isError && (
            <p className="px-3 py-10 text-center text-sm text-danger">
              Couldn&apos;t load reports{error instanceof Error ? `: ${error.message}` : "."}
            </p>
          )}

          {!isLoading && !isError && items.length === 0 && (
            <div className="flex flex-col items-center gap-2 px-3 py-14 text-center">
              <FileSearch className="size-8 text-muted-foreground/60" />
              <p className="text-sm text-muted-foreground">
                {hasFilters ? "No reports match these filters." : "No reports yet."}
              </p>
              {hasFilters && (
                <Button variant="outline" size="sm" onClick={resetFilters}>
                  Reset filters
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="font-mono text-xs text-muted-foreground">
          {total === 0 ? "0 results" : `${firstShown}–${lastShown} of ${total}`}
          {isFetching && !isLoading && <span className="ml-2 text-primary">updating…</span>}
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
          >
            <ChevronLeft />
            Prev
          </Button>
          <span className="font-mono text-xs text-muted-foreground">
            {page} / {pageCount}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
            disabled={page >= pageCount}
          >
            Next
            <ChevronRight />
          </Button>
        </div>
      </div>
    </div>
  );
}
