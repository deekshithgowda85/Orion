"use client";

import { useEffect, useMemo } from "react";
import Link from "next/link";
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import { ArrowUpRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  WorkflowNode,
  type WorkflowFlowNode,
} from "@/components/workflows/WorkflowNode";
import { useResearchHistory } from "@/hooks/useResearchHistory";
import { useRunStatus } from "@/hooks/useRunStatus";
import { useSSEStream } from "@/hooks/useSSEStream";
import {
  ALL_NODE_IDS,
  GRAPH_EDGES,
  NODE_POSITIONS,
  deriveNodeStates,
} from "@/lib/workflow-graph";
import { useResearchStore } from "@/store/research";
import type { AgentEvent, HistoryItem, RunStatus } from "@/types/research";

// Defined at module scope so React Flow doesn't re-register node types each render.
const nodeTypes: NodeTypes = { workflow: WorkflowNode };

const NO_EVENTS: AgentEvent[] = [];

function historyToRun(item: HistoryItem): RunStatus {
  return {
    run_id: item.run_id,
    ticker: item.ticker,
    query: item.query,
    workflow_type: item.workflow_type,
    status: item.status,
    progress_pct: 0,
    current_step: null,
    conflict_count: item.conflict_count,
    confidence_score: item.confidence_score,
    started_at: item.started_at,
    completed_at: item.completed_at,
    duration_seconds: item.duration_seconds,
    error: null,
    errors: [],
  };
}

/** React Flow DAG of the agent workflow; the node currently executing pulses. */
export function WorkflowCanvas() {
  const startTracking = useResearchStore((s) => s.startTracking);

  // Find a run to visualise: a locally tracked one first, else any running run from history.
  const trackedRunning = useResearchStore((s) => {
    for (const run of s.activeRuns.values()) {
      if (run.ticker && run.status === "running") return run;
    }
    return undefined;
  });
  const { data: history } = useResearchHistory(
    { page: 1, page_size: 50 },
    { refetchIntervalMs: 10_000 },
  );
  const historyRunning = history?.items.find((i) => i.status === "running");

  const runId = trackedRunning?.run_id ?? historyRunning?.run_id ?? null;

  // Make sure the store knows about a run discovered through history.
  useEffect(() => {
    if (!trackedRunning && historyRunning) startTracking(historyToRun(historyRunning));
  }, [trackedRunning, historyRunning, startTracking]);

  useRunStatus(runId);
  useSSEStream(runId);

  const run = useResearchStore((s) => (runId ? s.activeRuns.get(runId) : undefined));
  const events = useResearchStore((s) => (runId ? s.events.get(runId) : undefined)) ?? NO_EVENTS;

  const states = useMemo(
    () => deriveNodeStates(events, run?.current_step ?? null, run?.status ?? null),
    [events, run?.current_step, run?.status],
  );

  const nodes = useMemo<WorkflowFlowNode[]>(
    () =>
      ALL_NODE_IDS.map((id) => ({
        id,
        type: "workflow",
        position: NODE_POSITIONS[id],
        data: { nodeId: id, state: states[id] },
        draggable: false,
      })),
    [states],
  );

  const edges = useMemo<Edge[]>(
    () =>
      GRAPH_EDGES.map(([source, target]) => {
        const flowing = states[target] === "active";
        const complete = states[source] === "done" && states[target] === "done";
        return {
          id: `${source}->${target}`,
          source,
          target,
          animated: flowing,
          style: {
            stroke: flowing ? "#533afd" : complete ? "#287c5b" : "#a8c3de",
            strokeWidth: flowing ? 2 : 1.5,
          },
        };
      }),
    [states],
  );

  const active = run && run.status === "running" ? run : undefined;

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle>Agent workflow</CardTitle>
          <CardDescription>
            Trigger → Planner → data agents (in parallel) → Verifier → Synthesizer → Report
          </CardDescription>
        </div>
        {active ? (
          <div className="flex items-center gap-3">
            <Badge variant="cyan" className="font-mono">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-50" />
                <span className="relative inline-flex size-2 rounded-full bg-primary" />
              </span>
              {active.ticker} · {Math.round(active.progress_pct)}%
            </Badge>
            <Button asChild size="sm" variant="outline">
              <Link href={`/research/${active.run_id}`}>
                Watch live
                <ArrowUpRight />
              </Link>
            </Button>
          </div>
        ) : (
          <Badge variant="muted">No active run</Badge>
        )}
      </CardHeader>
      <CardContent>
        <div
          className="h-[440px] w-full overflow-hidden rounded-xl border border-border bg-surface"
          role="img"
          aria-label="Agent workflow graph"
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            minZoom={0.3}
            maxZoom={1.5}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#e3e8ee" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        {active?.current_step && (
          <p className="mt-3 text-sm text-muted-foreground">
            Currently executing: <span className="text-primary">{active.current_step}</span>
          </p>
        )}
      </CardContent>
    </Card>
  );
}
