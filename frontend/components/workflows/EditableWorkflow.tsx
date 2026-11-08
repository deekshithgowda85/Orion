"use client";

import {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  FileCheck2,
  FileText,
  GripVertical,
  ListTree,
  Maximize,
  Network,
  Newspaper,
  Plus,
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  TrendingUp,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { cn } from "@/lib/utils";

type NodeKind =
  | "trigger"
  | "planner"
  | "market_data"
  | "filings"
  | "news"
  | "quant"
  | "verifier"
  | "synthesizer"
  | "report";

type NodeConfig = {
  enabled: boolean;
  model?: string;
  temperature?: number;
  maxTokens?: number;
  timeoutSec?: number;
  retries?: number;
  triggerKind?: "manual" | "cron" | "webhook";
  cron?: string;
  confidenceThreshold?: number;
  maxIterations?: number;
  requireApproval?: boolean;
  approvalTimeoutMin?: number;
};

type EditorNodeData = { kind: NodeKind; label: string; config: NodeConfig };
type EditorNode = Node<EditorNodeData, "editor">;
type Tone = "warm" | "indigo" | "green";

const MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"];
const DND_TYPE = "application/orion-workflow-node";
const STORAGE_KEY = "orion.workflow.v1";
const MARKER = { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#a8c3de" } as const;

const META: Record<NodeKind, { label: string; icon: LucideIcon; tone: Tone; defaults: NodeConfig }> = {
  trigger: { label: "Trigger", icon: Zap, tone: "warm", defaults: { enabled: true, triggerKind: "manual", cron: "0 7 * * 1-5" } },
  planner: { label: "Planner", icon: ListTree, tone: "indigo", defaults: { enabled: true, model: MODELS[0], temperature: 0.2, maxTokens: 2500 } },
  market_data: { label: "Market Data", icon: TrendingUp, tone: "indigo", defaults: { enabled: true, model: MODELS[1], temperature: 0.1, maxTokens: 3000, timeoutSec: 120, retries: 2 } },
  filings: { label: "Filings", icon: FileText, tone: "indigo", defaults: { enabled: true, model: MODELS[1], temperature: 0.1, maxTokens: 3500, timeoutSec: 120, retries: 2 } },
  news: { label: "News", icon: Newspaper, tone: "indigo", defaults: { enabled: true, model: MODELS[1], temperature: 0.1, maxTokens: 2500, timeoutSec: 120, retries: 2 } },
  quant: { label: "Quant", icon: TrendingUp, tone: "indigo", defaults: { enabled: true, model: MODELS[0], temperature: 0.1, maxTokens: 2000 } },
  verifier: { label: "Verifier", icon: ShieldCheck, tone: "green", defaults: { enabled: true, model: MODELS[0], temperature: 0.1, maxTokens: 4000, confidenceThreshold: 0.6, maxIterations: 5 } },
  synthesizer: { label: "Synthesizer", icon: Sparkles, tone: "indigo", defaults: { enabled: true, model: MODELS[0], temperature: 0.2, maxTokens: 8000 } },
  report: { label: "Report", icon: FileCheck2, tone: "green", defaults: { enabled: true, requireApproval: true, approvalTimeoutMin: 5 } },
};

const KINDS = Object.keys(META) as NodeKind[];

function defaultNodes(): EditorNode[] {
  const node = (id: NodeKind, x: number, y: number): EditorNode => ({
    id,
    type: "editor",
    position: { x, y },
    data: { kind: id, label: META[id].label, config: { ...META[id].defaults } },
  });
  return [
    node("trigger", 0, 170),
    node("planner", 260, 170),
    node("market_data", 540, 20),
    node("filings", 540, 120),
    node("news", 540, 220),
    node("quant", 540, 320),
    node("verifier", 820, 170),
    node("synthesizer", 1080, 170),
    node("report", 1340, 170),
  ];
}

function defaultEdges(): Edge[] {
  const link = (source: string, target: string): Edge => ({
    id: `${source}-${target}`,
    source,
    target,
    type: "default",
    markerEnd: MARKER,
  });
  return [
    link("trigger", "planner"),
    ...["market_data", "filings", "news", "quant"].map((id) => link("planner", id)),
    ...["market_data", "filings", "news", "quant"].map((id) => link(id, "verifier")),
    link("verifier", "synthesizer"),
    link("synthesizer", "report"),
  ];
}

function nodeSummary(node: EditorNodeData) {
  if (!node.config.enabled) return "Disabled";
  if (node.kind === "trigger") return node.config.triggerKind === "cron" ? `Cron · ${node.config.cron}` : node.config.triggerKind;
  if (node.kind === "verifier") return `Min ${node.config.confidenceThreshold ?? 0.6} · ${node.config.maxIterations ?? 5} passes`;
  return node.config.model ?? "Configured";
}

function EditorNodeView({ data, selected }: NodeProps<EditorNode>) {
  const meta = META[data.kind];
  const Icon = meta.icon;
  return (
    <div className={cn(
      "relative flex min-w-[190px] items-center gap-3 rounded-xl border bg-card px-3 py-2.5 shadow-sm transition",
      selected ? "border-primary ring-2 ring-primary/15" : "border-border",
      !data.config.enabled && "opacity-50",
    )}>
      {data.kind !== "trigger" && <Handle type="target" position={Position.Left} className="!size-2 !border-border !bg-muted-foreground" />}
      <span className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-lg ring-1",
        meta.tone === "warm" && "bg-card-elevated text-warning ring-warning/20",
        meta.tone === "indigo" && "bg-primary/10 text-primary ring-primary/20",
        meta.tone === "green" && "bg-success/10 text-success ring-success/20",
      )}><Icon className="size-4" /></span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold">{data.label}</span>
        <span className="block truncate text-[11px] text-muted-foreground">{nodeSummary(data)}</span>
      </span>
      {data.kind !== "report" && <Handle type="source" position={Position.Right} className="!size-2 !border-border !bg-muted-foreground" />}
    </div>
  );
}

const nodeTypes: NodeTypes = { editor: EditorNodeView };

function reaches(edges: Edge[], from: string, to: string) {
  const seen = new Set<string>();
  const stack = [from];
  while (stack.length) {
    const current = stack.pop();
    if (!current || seen.has(current)) continue;
    if (current === to) return true;
    seen.add(current);
    edges.filter((edge) => edge.source === current).forEach((edge) => stack.push(edge.target));
  }
  return false;
}

function Inspector({ node, update, remove, close }: {
  node: EditorNode;
  update: (patch: Partial<EditorNodeData>) => void;
  remove: () => void;
  close: () => void;
}) {
  const { kind, label, config } = node.data;
  const setConfig = (patch: Partial<NodeConfig>) => update({ config: { ...config, ...patch } });
  const field = "w-full rounded-lg border border-border bg-background px-2.5 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10";
  return (
    <aside className="workflow-editor-inspector">
      <header className="flex items-center justify-between border-b border-border p-3">
        <div><p className="text-sm font-semibold">{META[kind].label} settings</p><p className="text-xs text-muted-foreground">Edit node configuration</p></div>
        <button type="button" onClick={close} className="rounded-md p-1 text-muted-foreground hover:bg-muted" aria-label="Close settings"><X className="size-4" /></button>
      </header>
      <div className="space-y-4 overflow-y-auto p-3">
        <label className="block space-y-1.5 text-xs font-medium text-muted-foreground">Name<input className={field} value={label} maxLength={40} onChange={(event) => update({ label: event.target.value })} /></label>
        <label className="flex items-center justify-between text-xs font-medium text-muted-foreground">Enabled<input type="checkbox" checked={config.enabled} onChange={(event) => setConfig({ enabled: event.target.checked })} /></label>
        {kind === "trigger" && <label className="block space-y-1.5 text-xs font-medium text-muted-foreground">Start with<select className={field} value={config.triggerKind} onChange={(event) => setConfig({ triggerKind: event.target.value as NodeConfig["triggerKind"] })}><option value="manual">Manual</option><option value="cron">Schedule (cron)</option><option value="webhook">Webhook event</option></select></label>}
        {kind === "trigger" && config.triggerKind === "cron" && <label className="block space-y-1.5 text-xs font-medium text-muted-foreground">Cron expression<input className={cn(field, "font-mono")} value={config.cron ?? ""} onChange={(event) => setConfig({ cron: event.target.value })} /></label>}
        {kind !== "trigger" && kind !== "report" && <label className="block space-y-1.5 text-xs font-medium text-muted-foreground">Model<select className={cn(field, "font-mono")} value={config.model} onChange={(event) => setConfig({ model: event.target.value })}>{MODELS.map((model) => <option key={model}>{model}</option>)}</select></label>}
        {kind !== "trigger" && kind !== "report" && <div className="grid grid-cols-2 gap-2"><label className="space-y-1.5 text-xs font-medium text-muted-foreground">Temperature<input className={field} type="number" min={0} max={1} step={0.05} value={config.temperature ?? ""} onChange={(event) => setConfig({ temperature: Number(event.target.value) })} /></label><label className="space-y-1.5 text-xs font-medium text-muted-foreground">Max tokens<input className={field} type="number" min={256} value={config.maxTokens ?? ""} onChange={(event) => setConfig({ maxTokens: Number(event.target.value) })} /></label></div>}
        {["market_data", "filings", "news"].includes(kind) && <div className="grid grid-cols-2 gap-2"><label className="space-y-1.5 text-xs font-medium text-muted-foreground">Timeout<input className={field} type="number" min={5} value={config.timeoutSec ?? ""} onChange={(event) => setConfig({ timeoutSec: Number(event.target.value) })} /></label><label className="space-y-1.5 text-xs font-medium text-muted-foreground">Retries<input className={field} type="number" min={0} max={5} value={config.retries ?? ""} onChange={(event) => setConfig({ retries: Number(event.target.value) })} /></label></div>}
        {kind === "verifier" && <div className="grid grid-cols-2 gap-2"><label className="space-y-1.5 text-xs font-medium text-muted-foreground">Confidence<input className={field} type="number" min={0} max={1} step={0.05} value={config.confidenceThreshold ?? ""} onChange={(event) => setConfig({ confidenceThreshold: Number(event.target.value) })} /></label><label className="space-y-1.5 text-xs font-medium text-muted-foreground">Max passes<input className={field} type="number" min={1} max={10} value={config.maxIterations ?? ""} onChange={(event) => setConfig({ maxIterations: Number(event.target.value) })} /></label></div>}
        {kind === "report" && <><label className="flex items-center justify-between text-xs font-medium text-muted-foreground">Human approval<input type="checkbox" checked={!!config.requireApproval} onChange={(event) => setConfig({ requireApproval: event.target.checked })} /></label>{config.requireApproval && <label className="block space-y-1.5 text-xs font-medium text-muted-foreground">Approval timeout<input className={field} type="number" min={1} max={60} value={config.approvalTimeoutMin ?? ""} onChange={(event) => setConfig({ approvalTimeoutMin: Number(event.target.value) })} /></label>}</>}
      </div>
      <footer className="border-t border-border p-3"><button type="button" onClick={remove} className="flex items-center gap-2 text-sm text-danger hover:underline"><Trash2 className="size-4" /> Delete node</button></footer>
    </aside>
  );
}

function EditorSurface() {
  const [nodes, setNodes, onNodesChange] = useNodesState<EditorNode>(defaultNodes());
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(defaultEdges());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [saved, setSaved] = useState("");
  const [saveMessage, setSaveMessage] = useState("Saved locally");
  const wrapper = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition, fitView, getNodes, getEdges } = useReactFlow<EditorNode, Edge>();
  const selected = nodes.find((node) => node.id === selectedId);
  const serialized = useMemo(() => JSON.stringify({ nodes, edges }), [nodes, edges]);
  const dirty = saved !== serialized;

  useEffect(() => {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) { setSaved(serialized); return; }
    try {
      const parsed = JSON.parse(raw) as { nodes?: EditorNode[]; edges?: Edge[] };
      if (parsed.nodes?.length && parsed.edges) { setNodes(parsed.nodes); setEdges(parsed.edges); setSaved(raw); return; }
    } catch { setSaveMessage("Could not load saved workflow"); }
    setSaved(serialized);
  // Load only once on mount; current state is intentionally the source for subsequent edits.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const issues = useMemo(() => {
    const result: string[] = [];
    if (!nodes.some((node) => node.data.kind === "trigger")) result.push("Add a Trigger node");
    if (!nodes.some((node) => node.data.kind === "report")) result.push("Add a Report node");
    nodes.forEach((node) => {
      if (node.data.kind !== "trigger" && !edges.some((edge) => edge.target === node.id)) result.push(`${node.data.label} has no input`);
      if (node.data.kind !== "report" && !edges.some((edge) => edge.source === node.id)) result.push(`${node.data.label} has no output`);
    });
    return result;
  }, [nodes, edges]);

  const addNode = useCallback((kind: NodeKind) => {
    const bounds = wrapper.current?.getBoundingClientRect();
    const point = bounds ? screenToFlowPosition({ x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2 }) : { x: 200, y: 200 };
    const id = `${kind}-${Date.now().toString(36)}`;
    setNodes((current) => [...current.map((node) => ({ ...node, selected: false })), { id, type: "editor", position: { x: point.x - 95, y: point.y - 30 }, selected: true, data: { kind, label: META[kind].label, config: { ...META[kind].defaults } } }]);
    setSelectedId(id);
    setMenuOpen(false);
  }, [screenToFlowPosition, setNodes]);

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return;
    const current = getEdges();
    const source = getNodes().find((node) => node.id === connection.source);
    const target = getNodes().find((node) => node.id === connection.target);
    if (!source || !target || source.data.kind === "report" || target.data.kind === "trigger" || current.some((edge) => edge.source === connection.source && edge.target === connection.target) || reaches(current, connection.target, connection.source)) return;
    setEdges((edgesState) => addEdge({ ...connection, markerEnd: MARKER }, edgesState));
  }, [getEdges, getNodes, setEdges]);

  const autoLayout = () => {
    const incoming = new Map(nodes.map((node) => [node.id, [] as string[]]));
    edges.forEach((edge) => incoming.get(edge.target)?.push(edge.source));
    const depth = (id: string, stack = new Set<string>()): number => {
      if (stack.has(id)) return 0;
      const parents = incoming.get(id) ?? [];
      if (!parents.length) return 0;
      const next = new Set(stack).add(id);
      return Math.max(...parents.map((parent) => depth(parent, next))) + 1;
    };
    const grouped = new Map<number, EditorNode[]>();
    nodes.forEach((node) => { const level = depth(node.id); grouped.set(level, [...(grouped.get(level) ?? []), node]); });
    setNodes(nodes.map((node) => {
      const level = depth(node.id);
      const group = grouped.get(level) ?? [node];
      return { ...node, position: { x: level * 280, y: group.indexOf(node) * 100 + 80 } };
    }));
    requestAnimationFrame(() => fitView({ padding: 0.2, duration: 300 }));
  };

  const updateSelected = (patch: Partial<EditorNodeData>) => {
    if (!selectedId) return;
    setNodes((current) => current.map((node) => node.id === selectedId ? { ...node, data: { ...node.data, ...patch } } : node));
  };
  const removeSelected = () => {
    if (!selectedId) return;
    setNodes((current) => current.filter((node) => node.id !== selectedId));
    setEdges((current) => current.filter((edge) => edge.source !== selectedId && edge.target !== selectedId));
    setSelectedId(null);
  };
  const save = () => {
    window.localStorage.setItem(STORAGE_KEY, serialized);
    setSaved(serialized);
    setSaveMessage("Saved locally");
  };
  const reset = () => {
    if (dirty && !window.confirm("Discard unsaved changes and restore the default workflow?")) return;
    setNodes(defaultNodes()); setEdges(defaultEdges()); setSelectedId(null); setSaveMessage("Reset to default");
    requestAnimationFrame(() => fitView({ padding: 0.2, duration: 300 }));
  };

  return (
    <div className="workflow-editor-workspace">
      <aside className="workflow-editor-leftbar">
        <div className="border-b border-border px-4 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Nodes</p>
          <p className="mt-1 text-xs text-muted-foreground">Drag a node onto the canvas</p>
        </div>
        <div className="space-y-5 overflow-y-auto p-3">
          {(["trigger", "planner", "market_data", "filings", "news", "quant", "verifier", "synthesizer", "report"] as NodeKind[]).map((kind) => {
            const Icon = META[kind].icon;
            return (
              <button
                key={kind}
                type="button"
                draggable
                onDragStart={(event) => event.dataTransfer.setData(DND_TYPE, kind)}
                onClick={() => addNode(kind)}
                className="workflow-editor-node-option"
              >
                <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="size-4" />
                </span>
                <span className="min-w-0 text-left">
                  <span className="block truncate text-xs font-medium">{META[kind].label}</span>
                  <span className="block truncate text-[10px] text-muted-foreground">
                    {kind === "trigger" ? "Start workflow" : kind === "report" ? "Workflow output" : "Agent node"}
                  </span>
                </span>
                <GripVertical className="ml-auto size-3.5 shrink-0 text-muted-foreground" />
              </button>
            );
          })}
        </div>
      </aside>
      <section className="workflow-editor-main">
        <div className="workflow-editor-toolbar">
        <div className="flex flex-wrap gap-2">
          <div className="relative">
            <button type="button" onClick={() => setMenuOpen((open) => !open)} className="inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground"><Plus className="size-4" /> Add node <ChevronDown className="size-4" /></button>
            {menuOpen && <div className="absolute left-0 top-11 z-20 w-56 rounded-xl border border-border bg-card p-2 shadow-lg">{KINDS.map((kind) => { const Icon = META[kind].icon; return <button key={kind} type="button" draggable onDragStart={(event) => event.dataTransfer.setData(DND_TYPE, kind)} onClick={() => addNode(kind)} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-muted"><Icon className="size-4 text-primary" />{META[kind].label}<GripVertical className="ml-auto size-3.5 text-muted-foreground" /></button>; })}</div>}
          </div>
          <button type="button" onClick={autoLayout} className="inline-flex h-9 items-center gap-2 rounded-lg border border-border px-3 text-sm hover:bg-muted"><Network className="size-4" /> Auto layout</button>
          <button type="button" onClick={() => fitView({ padding: 0.2, duration: 300 })} className="inline-flex h-9 items-center gap-2 rounded-lg border border-border px-3 text-sm hover:bg-muted"><Maximize className="size-4" /> Fit</button>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {issues.length ? <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2.5 py-1 text-warning"><AlertTriangle className="size-3.5" /> {issues.length} issue{issues.length === 1 ? "" : "s"}</span> : <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2.5 py-1 text-success"><CheckCircle2 className="size-3.5" /> Valid</span>}
          <span className="text-muted-foreground">{dirty ? "Unsaved changes" : saveMessage}</span>
          <button type="button" onClick={reset} className="inline-flex h-9 items-center gap-2 rounded-lg border border-border px-3 text-sm hover:bg-muted"><RotateCcw className="size-4" /> Reset</button>
          <button type="button" onClick={save} disabled={!dirty || !!issues.length} className="inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"><Save className="size-4" /> Save</button>
        </div>
        </div>
        <div ref={wrapper} className="workflow-editor-canvas" onDrop={(event: DragEvent) => { event.preventDefault(); const kind = event.dataTransfer.getData(DND_TYPE) as NodeKind; if (kind) addNode(kind); }} onDragOver={(event) => { event.preventDefault(); }}>
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeClick={(_, node) => setSelectedId(node.id)} onPaneClick={() => setSelectedId(null)} fitView fitViewOptions={{ padding: 0.18 }} minZoom={0.25} maxZoom={1.5} deleteKeyCode={["Backspace", "Delete"]} proOptions={{ hideAttribution: true }}>
          <Background variant={BackgroundVariant.Dots} gap={18} size={1.2} color="#e3e8ee" />
          <Controls showInteractive={false} />
          </ReactFlow>
          </div>
        </section>
        <aside className="workflow-editor-rightbar">
          {selected ? (
            <Inspector node={selected} update={updateSelected} remove={removeSelected} close={() => setSelectedId(null)} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center px-6 text-center">
              <div className="mb-3 flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Network className="size-5" />
              </div>
              <p className="text-sm font-medium">Node settings</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Select a node on the canvas to edit its configuration.
              </p>
            </div>
          )}
        </aside>
    </div>
  );
}

export function EditableWorkflow() {
  return <ReactFlowProvider><EditorSurface /></ReactFlowProvider>;
}
