"use client";

import { useMemo, useState } from "react";
import { ChevronRight, Wrench } from "lucide-react";
import { JsonViewer } from "@/components/JsonViewer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatMs, formatTokens } from "@/lib/format";
import { prettyAgentName } from "@/lib/sse";
import { cn } from "@/lib/utils";
import type { JsonValue, TraceEntry } from "@/types/research";

const PAGE = 50;

function entryToJson(e: TraceEntry): JsonValue {
  return {
    id: e.id,
    timestamp: e.timestamp,
    agent: e.agent,
    tool: e.tool,
    input: e.input,
    output_summary: e.output_summary,
    tokens_in: e.tokens_in,
    tokens_out: e.tokens_out,
    duration_ms: e.duration_ms,
    self_correction: e.self_correction,
  };
}

/** Every tool call with token counts and self-corrections, plus a JSON view of each. */
export function TraceLogView({ trace }: { trace: TraceEntry[] }) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [onlyCorrections, setOnlyCorrections] = useState(false);
  const [limit, setLimit] = useState(PAGE);

  const totals = useMemo(() => {
    let tokensIn = 0;
    let tokensOut = 0;
    let corrections = 0;
    for (const e of trace) {
      tokensIn += e.tokens_in;
      tokensOut += e.tokens_out;
      if (e.self_correction) corrections += 1;
    }
    return { tokensIn, tokensOut, corrections };
  }, [trace]);

  const filtered = onlyCorrections ? trace.filter((e) => e.self_correction) : trace;
  const rows = filtered.slice(0, limit);

  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  if (trace.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No trace entries recorded.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Badge variant="muted" className="font-mono">
          {trace.length} tool calls
        </Badge>
        <Badge variant="cyan" className="font-mono">
          {formatTokens(totals.tokensIn)} in · {formatTokens(totals.tokensOut)} out
        </Badge>
        <Badge variant={totals.corrections > 0 ? "amber" : "muted"} className="font-mono">
          {totals.corrections} self-corrections
        </Badge>
        <div className="ml-auto flex gap-2">
          <Button
            size="sm"
            variant={onlyCorrections ? "secondary" : "outline"}
            onClick={() => setOnlyCorrections((v) => !v)}
          >
            Self-corrections only
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              setOpen(open.size === rows.length ? new Set() : new Set(rows.map((r) => r.id)))
            }
          >
            {open.size === rows.length ? "Collapse all" : "Expand all"}
          </Button>
        </div>
      </div>

      <ol className="space-y-2">
        {rows.map((entry) => {
          const expanded = open.has(entry.id);
          return (
            <li key={entry.id} className="rounded-lg border border-border bg-surface">
              <button
                type="button"
                onClick={() => toggle(entry.id)}
                aria-expanded={expanded}
                className="flex w-full items-center gap-3 px-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
              >
                <ChevronRight
                  className={cn(
                    "size-4 shrink-0 text-muted-foreground transition-transform",
                    expanded && "rotate-90",
                  )}
                />
                <Wrench className="size-4 shrink-0 text-primary" />
                <span className="font-mono text-sm text-foreground">{entry.tool}</span>
                <span className="hidden text-xs text-muted-foreground sm:inline">
                  {prettyAgentName(entry.agent)}
                </span>
                {entry.self_correction && (
                  <Badge variant="amber" className="ml-1">
                    self-correction
                  </Badge>
                )}
                <span className="ml-auto flex items-center gap-3 font-mono text-[11px] tabular-nums text-muted-foreground">
                  <span>
                    {formatTokens(entry.tokens_in)}→{formatTokens(entry.tokens_out)} tok
                  </span>
                  <span>{formatMs(entry.duration_ms)}</span>
                </span>
              </button>

              {expanded && (
                <div className="space-y-3 border-t border-border px-4 py-3">
                  {entry.self_correction && (
                    <p className="rounded-md border border-amber/30 bg-amber/10 px-3 py-2 text-sm text-amber">
                      {entry.self_correction}
                    </p>
                  )}
                  <JsonViewer data={entryToJson(entry)} defaultExpandDepth={2} />
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {filtered.length > rows.length && (
        <div className="flex justify-center">
          <Button variant="outline" size="sm" onClick={() => setLimit((l) => l + PAGE)}>
            Show more ({filtered.length - rows.length} remaining)
          </Button>
        </div>
      )}
      {filtered.length === 0 && (
        <p className="py-4 text-center text-sm text-muted-foreground">No self-corrections recorded.</p>
      )}
    </div>
  );
}
