import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Priority, WorkflowType } from "@/types/research";

interface UIState {
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;

  defaultWorkflow: WorkflowType;
  defaultPriority: Priority;
  setDefaultWorkflow: (w: WorkflowType) => void;
  setDefaultPriority: (p: Priority) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

      defaultWorkflow: "deep_audit",
      defaultPriority: "standard",
      setDefaultWorkflow: (w) => set({ defaultWorkflow: w }),
      setDefaultPriority: (p) => set({ defaultPriority: p }),
    }),
    { name: "mra.ui" },
  ),
);
