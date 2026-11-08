"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { buildAgentEvent, isEventType, parseSSEData } from "@/lib/sse";
import { isTerminalStatus } from "@/lib/format";
import { useResearchStore } from "@/store/research";
import {
  SSE_EVENT_TYPES,
  type AgentEvent,
  type ConnectionState,
  type SSEEventType,
} from "@/types/research";

const EMPTY_EVENTS: AgentEvent[] = [];
const BASE_RETRY_SECONDS = 5;
const MAX_RETRY_SECONDS = 30;
/** After this many consecutive failures auto-reconnect stops and the user must click. */
const MAX_AUTO_RETRIES = 6;

export interface UseSSEStreamResult {
  events: AgentEvent[];
  connection: ConnectionState;
  /** Seconds until the next automatic reconnect attempt, or null when none is scheduled. */
  countdown: number | null;
  /** Reconnect immediately (also resets the retry budget). */
  reconnect: () => void;
}

/**
 * Opens GET /api/research/{run_id}/stream, feeds every typed event into the
 * Zustand store, and recovers from disconnects with an exponential-backoff
 * countdown plus a manual "reconnect now" escape hatch.
 *
 * Pass `null` to stay disconnected (e.g. while the run id is not known yet).
 */
export function useSSEStream(runId: string | null): UseSSEStreamResult {
  const events = useResearchStore((s) => (runId ? s.events.get(runId) : undefined)) ?? EMPTY_EVENTS;

  const [connection, setConnection] = useState<ConnectionState>("idle");
  const [countdown, setCountdown] = useState<number | null>(null);

  const esRef = useRef<EventSource | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptRef = useRef(0);
  const connectRef = useRef<() => void>(() => undefined);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setCountdown(null);
  }, []);

  const closeStream = useCallback(
    (id: string | null) => {
      esRef.current?.close();
      esRef.current = null;
      if (id) useResearchStore.getState().setConnection(id, null);
    },
    [],
  );

  const connect = useCallback(() => {
    if (!runId) return;

    clearTimer();
    closeStream(runId);

    const store = useResearchStore.getState();
    const known = store.activeRuns.get(runId);
    if (known && isTerminalStatus(known.status)) {
      setConnection("closed");
      return;
    }

    setConnection(attemptRef.current > 0 ? "reconnecting" : "connecting");

    const es = new EventSource(`/api/research/${encodeURIComponent(runId)}/stream`, {
      withCredentials: true,
    });
    esRef.current = es;
    store.setConnection(runId, es);

    es.onopen = () => {
      attemptRef.current = 0;
      clearTimer();
      setConnection("open");
    };

    const handleFrame = (msg: MessageEvent<string>, fallbackType?: SSEEventType) => {
      const frame = parseSSEData(msg.data, fallbackType);
      if (!frame) return; // heartbeat / malformed frame
      const event = buildAgentEvent(frame, msg.lastEventId);
      useResearchStore.getState().addEvent(runId, event);

      if (event.type === "report_ready" || event.type === "run_failed") {
        // Terminal event: the server will close the stream; don't treat that as an error.
        es.close();
        esRef.current = null;
        useResearchStore.getState().setConnection(runId, null);
        clearTimer();
        setConnection("closed");
      }
    };

    // Unnamed frames (`data: {"type": ..., "payload": ...}`)
    es.onmessage = (msg: MessageEvent<string>) => handleFrame(msg);

    // Named frames (`event: step_started`)
    for (const type of SSE_EVENT_TYPES) {
      es.addEventListener(type, (msg) => handleFrame(msg as MessageEvent<string>, type));
    }

    es.onerror = () => {
      es.close();
      if (esRef.current === es) esRef.current = null;
      useResearchStore.getState().setConnection(runId, null);

      const run = useResearchStore.getState().activeRuns.get(runId);
      if (run && isTerminalStatus(run.status)) {
        clearTimer();
        setConnection("closed");
        return;
      }

      attemptRef.current += 1;
      setConnection("disconnected");

      if (attemptRef.current > MAX_AUTO_RETRIES) {
        clearTimer();
        return; // manual reconnect only
      }

      const delay = Math.min(
        BASE_RETRY_SECONDS * 2 ** (attemptRef.current - 1),
        MAX_RETRY_SECONDS,
      );
      let remaining = delay;
      setCountdown(remaining);

      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
          connectRef.current();
        } else {
          setCountdown(remaining);
        }
      }, 1000);
    };
  }, [runId, clearTimer, closeStream]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // Open on mount / run change; always clean up.
  useEffect(() => {
    if (!runId) {
      setConnection("idle");
      return;
    }
    attemptRef.current = 0;
    connect();

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      closeStream(runId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  // If the status poller learns the run is already finished, stop retrying.
  const runStatus = useResearchStore((s) => (runId ? s.activeRuns.get(runId)?.status : undefined));
  useEffect(() => {
    if (runStatus && isTerminalStatus(runStatus)) {
      clearTimer();
      closeStream(runId);
      setConnection("closed");
    }
  }, [runStatus, runId, clearTimer, closeStream]);

  const reconnect = useCallback(() => {
    attemptRef.current = 0;
    connect();
  }, [connect]);

  return { events, connection, countdown, reconnect };
}

export { isEventType };
