"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Check } from "lucide-react";
import { NODE_STYLES, type NodeState, type WorkflowNodeId } from "@/lib/workflow-graph";
import { cn } from "@/lib/utils";

export type WorkflowNodeData = {
  nodeId: WorkflowNodeId;
  state: NodeState;
};

export type WorkflowFlowNode = Node<WorkflowNodeData, "workflow">;

/** Custom React Flow node: per-type icon + color, pulse while its agent is executing. */
export function WorkflowNode({ data }: NodeProps<WorkflowFlowNode>) {
  const style = NODE_STYLES[data.nodeId];
  const Icon = style.icon;
  const { state } = data;

  return (
    <div
      className={cn(
        "relative flex w-[190px] items-center gap-3 rounded-xl border bg-card px-3 py-2.5 transition-all",
        state === "idle" && cn(style.border, "opacity-90"),
        state === "active" && "node-pulse border-primary bg-card-elevated",
        state === "done" && "border-success/40 bg-card-elevated",
      )}
      aria-label={`${style.label}: ${state}`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-2 !border-border !bg-muted-foreground"
      />
      <div
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-lg ring-1",
          style.chip,
        )}
      >
        <Icon className="size-4" />
      </div>
      <div className="min-w-0">
        <p className="truncate font-heading text-sm font-semibold">{style.label}</p>
        <p className="truncate text-[11px] text-muted-foreground">{style.description}</p>
      </div>

      {state === "done" && (
        <span className="absolute -right-2 -top-2 flex size-5 items-center justify-center rounded-full bg-success text-background">
          <Check className="size-3" strokeWidth={3} />
        </span>
      )}
      {state === "active" && (
        <span className="absolute -right-1.5 -top-1.5 flex size-3">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-50" />
          <span className="relative inline-flex size-3 rounded-full bg-primary" />
        </span>
      )}

      <Handle
        type="source"
        position={Position.Right}
        className="!size-2 !border-border !bg-muted-foreground"
      />
    </div>
  );
}
