"use client";

import { AlertTriangle, Loader2, Timer } from "lucide-react";
import { ConfidenceBadge } from "@/components/ConfidenceBar";
import { RunIdDisplay } from "@/components/RunIdDisplay";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useElapsed } from "@/hooks/useElapsed";
import { formatClock, formatFullDateTime } from "@/lib/format";
import { WORKFLOW_LABELS } from "@/lib/workflows";
import { cn } from "@/lib/utils";
import type { RunStatus } from "@/types/research";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border/60 py-2.5 last:border-0">
      <dt className="shrink-0 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </dt>
      <dd className="min-w-0 text-right text-sm">{children}</dd>
    </div>
  );
}

export function RunMetadataPanel({ run }: { run: RunStatus }) {
  const running = run.status === "running" || run.status === "queued";
  const elapsed = useElapsed(run.started_at, run.completed_at, running);
  const pct = Math.round(run.progress_pct);

  return (
    <Card className="lg:sticky lg:top-20">
      <CardHeader>
        <CardTitle>Run metadata</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Progress */}
        <div className="space-y-2">
          <div className="flex items-end justify-between">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Progress
            </span>
            <span className="font-mono text-2xl font-semibold tabular-nums text-primary">{pct}%</span>
          </div>
          <Progress value={run.progress_pct} className="h-2.5" />
          <div className="flex min-h-5 items-center gap-2 text-sm text-muted-foreground">
            {running && run.current_step ? (
              <span key={run.current_step} className="inline-flex animate-in-up items-center gap-2">
                <Loader2 className="size-3.5 animate-spin text-primary" />
                <span className="truncate text-foreground">{run.current_step}</span>
                <span className="animate-pulse text-primary">…</span>
              </span>
            ) : run.status === "completed" ? (
              <span className="text-success">All steps complete</span>
            ) : run.status === "failed" ? (
              <span className="text-danger">Run stopped</span>
            ) : (
              <span>Waiting to start…</span>
            )}
          </div>
        </div>

        {/* Live counters */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-border bg-surface p-3">
            <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
              <Timer className="size-3" /> Elapsed
            </p>
            <p className="mt-1 font-mono text-xl tabular-nums">{formatClock(elapsed)}</p>
          </div>
          <div
            className={cn(
              "rounded-lg border p-3",
              run.conflict_count > 0 ? "border-amber/30 bg-amber/5" : "border-border bg-surface",
            )}
          >
            <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
              <AlertTriangle className="size-3" /> Conflicts
            </p>
            <p
              key={run.conflict_count}
              className={cn(
                "mt-1 animate-in-up font-mono text-xl tabular-nums",
                run.conflict_count > 0 && "text-amber",
              )}
            >
              {run.conflict_count}
            </p>
          </div>
        </div>

        {/* Facts */}
        <dl>
          <Row label="Run ID">
            <RunIdDisplay runId={run.run_id} truncate={18} />
          </Row>
          <Row label="Ticker">
            <span className="font-mono text-base font-semibold text-primary">{run.ticker || "—"}</span>
          </Row>
          <Row label="Workflow">
            <Badge variant="default">{WORKFLOW_LABELS[run.workflow_type]}</Badge>
          </Row>
          <Row label="Status">
            <StatusBadge status={run.status} />
          </Row>
          {run.confidence_score !== null && (
            <Row label="Confidence">
              <ConfidenceBadge score={run.confidence_score} />
            </Row>
          )}
          <Row label="Started">
            <span className="font-mono text-xs text-muted-foreground">
              {formatFullDateTime(run.started_at)}
            </span>
          </Row>
          <Row label="Query">
            <span className="text-left text-muted-foreground">{run.query || "—"}</span>
          </Row>
        </dl>

        {run.errors.length > 0 && (
          <div role="status" className="rounded-lg border border-amber/30 bg-amber/5 px-3 py-2 text-xs text-amber">
            <p className="mb-1 font-medium">
              {run.errors.length} source {run.errors.length === 1 ? "error" : "errors"}
            </p>
            <ul className="space-y-0.5 font-mono text-foreground/80">
              {run.errors.slice(0, 5).map((e, i) => (
                <li key={i} className="break-words">• {e}</li>
              ))}
              {run.errors.length > 5 && <li>… and {run.errors.length - 5} more</li>}
            </ul>
          </div>
        )}

        {run.status === "failed" && run.error && (
          <p
            role="alert"
            className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {run.error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
