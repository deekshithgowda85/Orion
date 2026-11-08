import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ScheduledWorkflow, WorkflowType } from "@/types/research";

/**
 * The BFF exposes no schedule endpoints yet, so scheduled workflows are kept
 * client-side (localStorage). Swap this store for a TanStack Query hook once a
 * schedules API exists — the UI only depends on this interface.
 */
interface SchedulesState {
  schedules: ScheduledWorkflow[];
  addSchedule: (input: { ticker: string; workflow_type: WorkflowType; cron: string }) => void;
  toggleSchedule: (id: string, enabled: boolean) => void;
  removeSchedule: (id: string) => void;
}

function makeId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `sch_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

export const useSchedulesStore = create<SchedulesState>()(
  persist(
    (set) => ({
      schedules: [],
      addSchedule: (input) =>
        set((state) => ({
          schedules: [
            ...state.schedules,
            {
              id: makeId(),
              ticker: input.ticker,
              workflow_type: input.workflow_type,
              cron: input.cron,
              enabled: true,
              created_at: new Date().toISOString(),
            },
          ],
        })),
      toggleSchedule: (id, enabled) =>
        set((state) => ({
          schedules: state.schedules.map((s) => (s.id === id ? { ...s, enabled } : s)),
        })),
      removeSchedule: (id) =>
        set((state) => ({ schedules: state.schedules.filter((s) => s.id !== id) })),
    }),
    { name: "mra.schedules" },
  ),
);
