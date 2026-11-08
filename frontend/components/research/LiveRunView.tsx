"use client";

import { useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { ActivityFeed } from "@/components/research/ActivityFeed";
import { ReportViewer } from "@/components/research/ReportViewer";
import { RunMetadataPanel } from "@/components/research/RunMetadataPanel";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRunReport } from "@/hooks/useRunReport";
import { useRunStatus } from "@/hooks/useRunStatus";
import { useSSEStream } from "@/hooks/useSSEStream";
import { isTerminalStatus } from "@/lib/format";
import { useResearchStore } from "@/store/research";
import type { AgentEvent, RunStatus } from "@/types/research";

const NO_EVENTS: AgentEvent[] = [];

function placeholderRun(runId: string): RunStatus {
  return {
    run_id: runId,
    ticker: "",
    query: "",
    workflow_type: "deep_audit",
    status: "queued",
    progress_pct: 0,
    current_step: null,
    conflict_count: 0,
    confidence_score: null,
    started_at: null,
    completed_at: null,
    duration_seconds: null,
    error: null,
    errors: [],
  };
}

export function LiveRunView({ runId }: { runId: string }) {
  const queryClient = useQueryClient();
  const startTracking = useResearchStore((s) => s.startTracking);
  const reportRef = useRef<HTMLDivElement>(null);

  // Declared first so the run exists in the store before SSE events start arriving.
  useEffect(() => {
    startTracking(placeholderRun(runId));
  }, [runId, startTracking]);

  const statusQuery = useRunStatus(runId);

  // Don't open a stream for runs the server already reports as finished (or missing).
  const serverStatus = statusQuery.data?.status;
  const canStream = !statusQuery.isError && !(serverStatus && isTerminalStatus(serverStatus));
  const stream = useSSEStream(canStream ? runId : null);

  const run = useResearchStore((s) => s.activeRuns.get(runId));
  const events = useResearchStore((s) => s.events.get(runId)) ?? NO_EVENTS;

  const status = run?.status ?? serverStatus;
  const finished = status ? isTerminalStatus(status) : false;
  const reportQuery = useRunReport(runId, status);

  // Once the run finishes (via SSE or polling) refresh server state that depends on it.
  useEffect(() => {
    if (status === "completed" || status === "failed") {
      void queryClient.invalidateQueries({ queryKey: ["run-status", runId] });
      void queryClient.invalidateQueries({ queryKey: ["research-history"] });
    }
  }, [status, runId, queryClient]);

  const scrollToReport = useCallback(() => {
    reportRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // Bring the report into view the first time it renders after a live run.
  const hadLiveEvents = useRef(false);
  useEffect(() => {
    if (events.length > 0) hadLiveEvents.current = true;
  }, [events.length]);
  const reportReady = reportQuery.isSuccess;
  useEffect(() => {
    if (reportReady && hadLiveEvents.current) scrollToReport();
  }, [reportReady, scrollToReport]);

  /* ----------------------------- Error / loading ----------------------------- */

  if (statusQuery.isError && !run?.ticker) {
    return (
      <div className="mx-auto max-w-xl">
        <Card>
          <CardContent className="space-y-4 p-8 text-center">
            <p className="font-heading text-lg font-semibold">Couldn&apos;t load this run</p>
            <p className="text-sm text-muted-foreground">
              {statusQuery.error instanceof Error ? statusQuery.error.message : "Unknown error."}
            </p>
            <div className="flex justify-center gap-2">
              <Button variant="outline" onClick={() => void statusQuery.refetch()}>
                <RefreshCw />
                Retry
              </Button>
              <Button asChild variant="ghost">
                <Link href="/">Back to overview</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const title = run?.ticker ? `${run.ticker} research run` : "Research run";

  return (
    <>
      <PageHeader
        title={title}
        description={run?.query || "Streaming live from the agent workflow."}
        actions={
          <Button asChild variant="ghost" size="sm">
            <Link href="/">
              <ArrowLeft />
              Overview
            </Link>
          </Button>
        }
      />

      {/* Split panel: 60% activity feed / 40% metadata */}
      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <ActivityFeed
          events={events}
          connection={finished ? "closed" : stream.connection}
          countdown={stream.countdown}
          runFinished={finished}
          onReconnect={stream.reconnect}
          onViewReport={scrollToReport}
        />
        {run ? (
          <RunMetadataPanel run={run} />
        ) : (
          <Skeleton className="h-[520px] w-full rounded-xl" />
        )}
      </div>

      {/* Report */}
      <div ref={reportRef} id="report" className="mt-8 scroll-mt-20">
        {status === "completed" && reportQuery.isLoading && (
          <Skeleton className="h-[420px] w-full rounded-xl" />
        )}

        {status === "completed" && reportQuery.isError && (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
              <p className="text-sm text-danger">
                Couldn&apos;t load the report
                {reportQuery.error instanceof Error ? `: ${reportQuery.error.message}` : "."}
              </p>
              <Button variant="outline" size="sm" onClick={() => void reportQuery.refetch()}>
                <RefreshCw />
                Retry
              </Button>
            </CardContent>
          </Card>
        )}

        {status === "failed" && (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
              <p className="font-heading text-lg font-semibold text-danger">This run failed</p>
              <p className="max-w-xl text-sm text-muted-foreground">
                {run?.error ?? "The workflow stopped before a report could be produced."}
              </p>
              <Button asChild variant="outline" size="sm">
                <Link href="/research/new">Start a new research run</Link>
              </Button>
            </CardContent>
          </Card>
        )}

        {reportQuery.data && <ReportViewer report={reportQuery.data} />}
      </div>
    </>
  );
}
