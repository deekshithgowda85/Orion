"use client";

import { format } from "date-fns";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  FileCheck2,
  Loader2,
  PlayCircle,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatMs } from "@/lib/format";
import { prettyAgentName } from "@/lib/sse";
import { cn } from "@/lib/utils";
import type { AgentEvent } from "@/types/research";

interface AgentEventCardProps {
  event: AgentEvent;
  /** For step_started: true while no matching step_completed has arrived. */
  isActive?: boolean;
  onViewReport?: () => void;
  className?: string;
}

function Shell({
  icon,
  tone,
  time,
  children,
  className,
}: {
  icon: React.ReactNode;
  tone: string;
  time: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-full border",
            tone,
          )}
        >
          {icon}
        </div>
        <div className="mt-1 w-px flex-1 bg-border" aria-hidden />
      </div>
      <div className={cn("min-w-0 flex-1 pb-5", className)}>
        {children}
        <p className="mt-1 font-mono text-[11px] text-muted-foreground/70">
          {format(time, "HH:mm:ss")}
        </p>
      </div>
    </div>
  );
}

/** Renders one SSE event as a timeline entry. */
export function AgentEventCard({ event, isActive, onViewReport, className }: AgentEventCardProps) {
  const wrapper = cn("animate-in-up", className);

  switch (event.type) {
    case "run_started":
      return (
        <div className={wrapper}>
          <Shell
            time={event.receivedAt}
            tone="border-primary/40 bg-primary/10 text-primary"
            icon={<PlayCircle className="size-4" />}
          >
            <p className="text-sm font-medium">Run started</p>
            <p className="text-sm text-muted-foreground">{event.payload.message}</p>
          </Shell>
        </div>
      );

    case "progress":
      return (
        <div className={wrapper}>
          <Shell
            time={event.receivedAt}
            tone="border-border bg-muted text-muted-foreground"
            icon={<Activity className="size-4" />}
          >
            <p className="text-sm text-muted-foreground">
              Progress{" "}
              <span className="font-mono text-foreground">
                {Math.round(event.payload.progress_pct)}%
              </span>
              {event.payload.current_step ? ` — ${event.payload.current_step}` : null}
            </p>
          </Shell>
        </div>
      );

    case "step_started":
      return (
        <div className={wrapper}>
          <Shell
            time={event.receivedAt}
            tone={
              isActive
                ? "border-primary/25 bg-primary/10 text-primary"
                : "border-border bg-muted text-muted-foreground"
            }
            icon={
              isActive ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <PlayCircle className="size-4" />
              )
            }
          >
            <p className="text-sm font-medium">
              <span className="font-mono text-primary">{prettyAgentName(event.payload.agent)}</span>{" "}
              <span className="text-muted-foreground">started</span>
            </p>
            <p className="text-sm text-muted-foreground">{event.payload.label}</p>
          </Shell>
        </div>
      );

    case "step_completed":
      return (
        <div className={wrapper}>
          <Shell
            time={event.receivedAt}
            tone="border-success/40 bg-success/10 text-success"
            icon={<CheckCircle2 className="size-4" />}
          >
            <p className="flex flex-wrap items-center gap-x-2 text-sm font-medium">
              <span className="font-mono text-primary">{prettyAgentName(event.payload.agent)}</span>
              <span className="text-muted-foreground">completed</span>
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">
                {formatMs(event.payload.duration_ms)}
              </span>
            </p>
            {event.payload.summary && (
              <p className="mt-0.5 text-sm text-muted-foreground">{event.payload.summary}</p>
            )}
          </Shell>
        </div>
      );

    case "conflict_found":
      return (
        <div className={wrapper}>
          <Shell
            time={event.receivedAt}
            tone="border-amber/40 bg-amber/10 text-amber"
            icon={<AlertTriangle className="size-4" />}
          >
            <div className="rounded-lg border border-amber/30 bg-amber/5 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-amber">
                  Data conflict · <span className="font-mono">{event.payload.metric}</span>
                </p>
                {event.payload.severity && (
                  <span className="rounded-full border border-amber/30 px-2 py-0.5 text-[10px] uppercase tracking-wider text-amber">
                    {event.payload.severity}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <ConflictSide value={event.payload.value_a} source={event.payload.source_a} />
                <ConflictSide value={event.payload.value_b} source={event.payload.source_b} />
              </div>
              {event.payload.resolution && (
                <p className="mt-2 text-xs text-muted-foreground">
                  <span className="text-foreground">Resolution:</span> {event.payload.resolution}
                </p>
              )}
            </div>
          </Shell>
        </div>
      );

    case "report_ready":
      return (
        <div className={wrapper}>
          <Shell
            time={event.receivedAt}
            tone="border-success/40 bg-success/15 text-success"
            icon={<FileCheck2 className="size-4" />}
          >
            <p className="text-sm font-medium text-success">Report ready</p>
            {event.payload.confidence_score !== null && (
              <p className="text-sm text-muted-foreground">
                Overall confidence{" "}
                <span className="font-mono text-foreground">
                  {event.payload.confidence_score.toFixed(2)}
                </span>
              </p>
            )}
            {onViewReport && (
              <Button size="sm" className="mt-2" onClick={onViewReport}>
                View Report
              </Button>
            )}
          </Shell>
        </div>
      );

    case "run_failed":
      return (
        <div className={wrapper}>
          <Shell
            time={event.receivedAt}
            tone="border-danger/40 bg-danger/10 text-danger"
            icon={<XCircle className="size-4" />}
          >
            <p className="text-sm font-medium text-danger">Run failed</p>
            <p className="text-sm text-muted-foreground">{event.payload.error}</p>
          </Shell>
        </div>
      );
  }
}

function ConflictSide({ value, source }: { value: string; source: string }) {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2">
      <p className="font-mono text-base text-foreground">{value || "—"}</p>
      <p className="truncate text-xs text-muted-foreground" title={source}>
        {source}
      </p>
    </div>
  );
}
