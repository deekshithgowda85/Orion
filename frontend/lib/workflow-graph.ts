import {
  Calculator,
  FileCheck2,
  FileText,
  ListTree,
  Newspaper,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Zap,
  type LucideIcon,
} from "lucide-react";
import type { AgentEvent } from "@/types/research";

export type WorkflowNodeId =
  | "trigger"
  | "planner"
  | "market_data"
  | "filings"
  | "news"
  | "quant"
  | "verifier"
  | "synthesizer"
  | "report";

export type NodeState = "idle" | "active" | "done";

export interface NodeStyle {
  icon: LucideIcon;
  /** Tailwind classes for the icon chip. */
  chip: string;
  /** Tailwind classes for the node border/glow when idle. */
  border: string;
  label: string;
  description: string;
}

export const NODE_STYLES: Record<WorkflowNodeId, NodeStyle> = {
  trigger: {
    icon: Zap,
    chip: "bg-amber/15 text-amber ring-amber/30",
    border: "border-amber/30",
    label: "Trigger",
    description: "Manual or scheduled start",
  },
  planner: {
    icon: ListTree,
    chip: "bg-primary/15 text-primary ring-primary/30",
    border: "border-primary/30",
    label: "Planner",
    description: "Decomposes the query",
  },
  market_data: {
    icon: TrendingUp,
    chip: "bg-cyan/10 text-cyan ring-cyan/30",
    border: "border-cyan/25",
    label: "Market Data",
    description: "Prices, volume, multiples",
  },
  filings: {
    icon: FileText,
    chip: "bg-cyan/10 text-cyan ring-cyan/30",
    border: "border-cyan/25",
    label: "Filings",
    description: "SEC filings & transcripts",
  },
  news: {
    icon: Newspaper,
    chip: "bg-cyan/10 text-cyan ring-cyan/30",
    border: "border-cyan/25",
    label: "News",
    description: "Headlines & sentiment",
  },
  quant: {
    icon: Calculator,
    chip: "bg-cyan/10 text-cyan ring-cyan/30",
    border: "border-cyan/25",
    label: "Quant",
    description: "Models & factor analysis",
  },
  verifier: {
    icon: ShieldCheck,
    chip: "bg-success/10 text-success ring-success/30",
    border: "border-success/30",
    label: "Verifier",
    description: "Cross-source conflict checks",
  },
  synthesizer: {
    icon: Sparkles,
    chip: "bg-primary/15 text-primary ring-primary/30",
    border: "border-primary/30",
    label: "Synthesizer",
    description: "Writes the narrative",
  },
  report: {
    icon: FileCheck2,
    chip: "bg-success/10 text-success ring-success/30",
    border: "border-success/30",
    label: "Report",
    description: "Cited, scored deliverable",
  },
};

export const NODE_POSITIONS: Record<WorkflowNodeId, { x: number; y: number }> = {
  trigger: { x: 0, y: 150 },
  planner: { x: 240, y: 150 },
  market_data: { x: 500, y: 0 },
  filings: { x: 500, y: 100 },
  news: { x: 500, y: 200 },
  quant: { x: 500, y: 300 },
  verifier: { x: 780, y: 150 },
  synthesizer: { x: 1030, y: 150 },
  report: { x: 1280, y: 150 },
};

export const GRAPH_EDGES: ReadonlyArray<readonly [WorkflowNodeId, WorkflowNodeId]> = [
  ["trigger", "planner"],
  ["planner", "market_data"],
  ["planner", "filings"],
  ["planner", "news"],
  ["planner", "quant"],
  ["market_data", "verifier"],
  ["filings", "verifier"],
  ["news", "verifier"],
  ["quant", "verifier"],
  ["verifier", "synthesizer"],
  ["synthesizer", "report"],
];

export const ALL_NODE_IDS = Object.keys(NODE_STYLES) as WorkflowNodeId[];

/** Maps an agent / step name from the backend to a canvas node. */
export function agentToNodeId(name: string | null | undefined): WorkflowNodeId | null {
  if (!name) return null;
  const n = name.toLowerCase();
  if (n.includes("trigger")) return "trigger";
  if (n.includes("plan")) return "planner";
  if (n.includes("market") || n.includes("price")) return "market_data";
  if (n.includes("filing") || n.includes("sec") || n.includes("edgar") || n.includes("10-k")) {
    return "filings";
  }
  if (n.includes("news") || n.includes("sentiment") || n.includes("headline")) return "news";
  if (n.includes("quant") || n.includes("model") || n.includes("factor")) return "quant";
  if (n.includes("verif") || n.includes("conflict") || n.includes("check")) return "verifier";
  if (n.includes("synth") || n.includes("writer") || n.includes("draft")) return "synthesizer";
  if (n.includes("report")) return "report";
  return null;
}

/** Folds the SSE event stream into a per-node state map. */
export function deriveNodeStates(
  events: AgentEvent[],
  currentStep: string | null,
  runStatus: "queued" | "running" | "completed" | "failed" | null,
): Record<WorkflowNodeId, NodeState> {
  const states = Object.fromEntries(ALL_NODE_IDS.map((id) => [id, "idle"])) as Record<
    WorkflowNodeId,
    NodeState
  >;

  if (runStatus === null) return states;
  states.trigger = "done";

  if (runStatus === "completed") {
    for (const id of ALL_NODE_IDS) states[id] = "done";
    return states;
  }

  for (const event of events) {
    if (event.type === "step_started") {
      const id = agentToNodeId(event.payload.agent) ?? agentToNodeId(event.payload.label);
      if (id) states[id] = "active";
    } else if (event.type === "step_completed") {
      const id = agentToNodeId(event.payload.agent) ?? agentToNodeId(event.payload.label);
      if (id) states[id] = "done";
    } else if (event.type === "report_ready") {
      for (const id of ALL_NODE_IDS) states[id] = "done";
    }
  }

  // No step events yet (e.g. joined mid-run): fall back to the status snapshot label.
  const anyActive = ALL_NODE_IDS.some((id) => states[id] === "active");
  if (!anyActive && runStatus === "running") {
    const id = agentToNodeId(currentStep);
    if (id) states[id] = "active";
  }

  return states;
}
