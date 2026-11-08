"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, Radio, RefreshCw, WifiOff } from "lucide-react";
import { AgentEventCard } from "@/components/AgentEventCard";
import { ConnectionPill } from "@/components/research/ConnectionPill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AgentEvent, ConnectionState } from "@/types/research";

interface ActivityFeedProps {
  events: AgentEvent[];
  connection: ConnectionState;
  /** Seconds until the next automatic reconnect, or null if none is scheduled. */
  countdown: number | null;
  runFinished: boolean;
  onReconnect: () => void;
  onViewReport: () => void;
}

/** Live timeline of agent events with auto-scroll and reconnect UI. */
export function ActivityFeed({
  events,
  connection,
  countdown,
  runFinished,
  onReconnect,
  onViewReport,
}: ActivityFeedProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  const [showJump, setShowJump] = useState(false);

  // `progress` frames only drive the metadata panel; keep the timeline readable.
  const visible = useMemo(() => events.filter((e) => e.type !== "progress"), [events]);

  // A step_started is "active" until a step_completed with the same step id arrives.
  const completedSteps = useMemo(() => {
    const set = new Set<string>();
    for (const e of events) {
      if (e.type === "step_completed") set.add(e.payload.step_id);
    }
    return set;
  }, [events]);

  const scrollToBottom = useCallback((smooth: boolean) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }, []);

  // Auto-scroll to the latest event unless the user scrolled up to read.
  useEffect(() => {
    if (stickRef.current) scrollToBottom(true);
  }, [visible.length, scrollToBottom]);

  const onScroll = () => {
    const el = scrollerRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    stickRef.current = nearBottom;
    setShowJump(!nearBottom);
  };

  const jumpToLatest = () => {
    stickRef.current = true;
    setShowJump(false);
    scrollToBottom(true);
  };

  return (
    <Card className="flex flex-col">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <Radio className="size-4 text-primary" />
          Live agent activity
        </CardTitle>
        <ConnectionPill state={connection} />
      </CardHeader>

      {connection === "disconnected" && !runFinished && (
        <div
          role="alert"
          className="mx-5 mb-2 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber/30 bg-amber/10 px-3 py-2"
        >
          <p className="flex items-center gap-2 text-sm text-amber">
            <WifiOff className="size-4" />
            {countdown !== null ? (
              <>
                Connection lost. Reconnecting in{" "}
                <span className="font-mono tabular-nums">{countdown}s</span>…
              </>
            ) : (
              "Connection lost. Automatic retries stopped."
            )}
          </p>
          <Button size="sm" variant="outline" onClick={onReconnect}>
            <RefreshCw />
            {countdown !== null ? "Reconnect now" : "Reconnect"}
          </Button>
        </div>
      )}

      <CardContent className="relative flex-1 pb-4">
        <div
          ref={scrollerRef}
          onScroll={onScroll}
          className="max-h-[calc(100vh-20rem)] min-h-[420px] overflow-y-auto pr-2"
          aria-live="polite"
          aria-label="Agent event timeline"
        >
          {visible.length === 0 ? (
            <div className="flex min-h-[380px] flex-col items-center justify-center gap-3 text-center">
              <span className="relative flex size-3">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-60" />
                <span className="relative inline-flex size-3 rounded-full bg-primary" />
              </span>
              <p className="text-sm text-muted-foreground">
                {runFinished
                  ? "This run has finished. Live events are only streamed while a run is in progress."
                  : "Waiting for the first agent event…"}
              </p>
            </div>
          ) : (
            <ol className="pt-1">
              {visible.map((event) => (
                <li key={event.id}>
                  <AgentEventCard
                    event={event}
                    isActive={
                      event.type === "step_started"
                        ? !completedSteps.has(event.payload.step_id) && !runFinished
                        : undefined
                    }
                    onViewReport={onViewReport}
                  />
                </li>
              ))}
            </ol>
          )}
        </div>

        {showJump && (
          <Button
            size="sm"
            variant="cyan"
            onClick={jumpToLatest}
            className="absolute bottom-6 left-1/2 -translate-x-1/2 shadow-lg"
          >
            <ArrowDown />
            Jump to latest
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
