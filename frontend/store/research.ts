import { create } from "zustand";
import { isTerminalStatus } from "@/lib/format";
import type { AgentEvent, RunStatus } from "@/types/research";

const MAX_EVENTS_PER_RUN = 500;

/** Applies a single SSE event to a run's status snapshot (pure). */
function applyEvent(run: RunStatus, ev: AgentEvent): RunStatus {
  const liveStatus = isTerminalStatus(run.status) ? run.status : "running";

  switch (ev.type) {
    case "run_started":
      return { ...run, status: liveStatus };

    case "progress":
      return {
        ...run,
        status: liveStatus,
        progress_pct: Math.max(run.progress_pct, ev.payload.progress_pct),
        current_step: ev.payload.current_step ?? run.current_step,
      };

    case "step_started":
      return {
        ...run,
        status: liveStatus,
        current_step: ev.payload.label,
        progress_pct: Math.max(run.progress_pct, ev.payload.progress_pct ?? run.progress_pct),
      };

    case "step_completed":
      return {
        ...run,
        status: liveStatus,
        progress_pct: Math.max(run.progress_pct, ev.payload.progress_pct ?? run.progress_pct),
      };

    case "conflict_found":
      return { ...run, conflict_count: run.conflict_count + 1 };

    case "report_ready":
      return {
        ...run,
        status: "completed",
        progress_pct: 100,
        current_step: null,
        confidence_score: ev.payload.confidence_score ?? run.confidence_score,
        completed_at: run.completed_at ?? new Date().toISOString(),
      };

    case "run_failed":
      return {
        ...run,
        status: "failed",
        current_step: null,
        error: ev.payload.error,
        completed_at: run.completed_at ?? new Date().toISOString(),
      };
  }
}

interface ResearchState {
  activeRuns: Map<string, RunStatus>;
  sseConnections: Map<string, EventSource>;
  events: Map<string, AgentEvent[]>;

  /** Begin tracking a run (no-op if already tracked). */
  startTracking: (run: RunStatus) => void;
  /** Shallow-merge a patch into a tracked run. */
  updateRunStatus: (runId: string, patch: Partial<RunStatus>) => void;
  /** Merge a snapshot from the status endpoint without regressing live SSE state. */
  syncRunStatus: (server: RunStatus) => void;
  /** Append an SSE event (deduped by id) and fold it into the run status. */
  addEvent: (runId: string, event: AgentEvent) => void;
  setConnection: (runId: string, es: EventSource | null) => void;
  /** Close the stream and forget the run. */
  stopTracking: (runId: string) => void;
  /** Close every stream and drop all tracked data (used when the Clerk organization changes). */
  reset: () => void;
}

export const useResearchStore = create<ResearchState>((set, get) => ({
  activeRuns: new Map(),
  sseConnections: new Map(),
  events: new Map(),

  startTracking: (run) => {
    if (get().activeRuns.has(run.run_id)) return;
    set((state) => {
      const activeRuns = new Map(state.activeRuns);
      activeRuns.set(run.run_id, run);
      return { activeRuns };
    });
  },

  updateRunStatus: (runId, patch) => {
    set((state) => {
      const current = state.activeRuns.get(runId);
      if (!current) return state;
      const activeRuns = new Map(state.activeRuns);
      activeRuns.set(runId, { ...current, ...patch });
      return { activeRuns };
    });
  },

  syncRunStatus: (server) => {
    set((state) => {
      const existing = state.activeRuns.get(server.run_id);
      const activeRuns = new Map(state.activeRuns);

      if (!existing) {
        activeRuns.set(server.run_id, server);
        return { activeRuns };
      }

      const keepLocalStatus = isTerminalStatus(existing.status) && !isTerminalStatus(server.status);
      const merged: RunStatus = {
        ...server,
        status: keepLocalStatus ? existing.status : server.status,
        progress_pct: Math.max(existing.progress_pct, server.progress_pct),
        conflict_count: Math.max(existing.conflict_count, server.conflict_count),
        current_step: server.current_step ?? existing.current_step,
        confidence_score: server.confidence_score ?? existing.confidence_score,
        started_at: server.started_at ?? existing.started_at,
        completed_at: server.completed_at ?? existing.completed_at,
        error: server.error ?? existing.error,
        errors: server.errors.length > 0 ? server.errors : existing.errors,
      };
      activeRuns.set(server.run_id, merged);
      return { activeRuns };
    });
  },

  addEvent: (runId, event) => {
    set((state) => {
      const currentEvents = state.events.get(runId) ?? [];
      if (currentEvents.some((e) => e.id === event.id)) return state;

      const nextEvents = [...currentEvents, event];
      if (nextEvents.length > MAX_EVENTS_PER_RUN) {
        nextEvents.splice(0, nextEvents.length - MAX_EVENTS_PER_RUN);
      }
      const events = new Map(state.events);
      events.set(runId, nextEvents);

      const run = state.activeRuns.get(runId);
      if (!run) return { events };

      const activeRuns = new Map(state.activeRuns);
      activeRuns.set(runId, applyEvent(run, event));
      return { events, activeRuns };
    });
  },

  setConnection: (runId, es) => {
    set((state) => {
      const sseConnections = new Map(state.sseConnections);
      if (es) sseConnections.set(runId, es);
      else sseConnections.delete(runId);
      return { sseConnections };
    });
  },

  stopTracking: (runId) => {
    const es = get().sseConnections.get(runId);
    es?.close();
    set((state) => {
      const activeRuns = new Map(state.activeRuns);
      const sseConnections = new Map(state.sseConnections);
      const events = new Map(state.events);
      activeRuns.delete(runId);
      sseConnections.delete(runId);
      events.delete(runId);
      return { activeRuns, sseConnections, events };
    });
  },

  reset: () => {
    get().sseConnections.forEach((es) => es.close());
    set({ activeRuns: new Map(), sseConnections: new Map(), events: new Map() });
  },
}));
