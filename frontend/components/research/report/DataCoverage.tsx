"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, CircleSlash } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ResearchReport } from "@/types/research";

function Chip({ ok, label }: { ok: boolean; label: string }) {
  const Icon = ok ? CheckCircle2 : CircleSlash;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
        ok
          ? "border-success/30 bg-success/10 text-success"
          : "border-amber/30 bg-amber/10 text-amber",
      )}
    >
      <Icon className="size-3.5" />
      {label}: {ok ? "available" : "not available"}
    </span>
  );
}

/** Shows which data sets made it into the report, plus the backend's non-fatal `errors` list. */
export function DataCoverage({ report }: { report: ResearchReport }) {
  const [open, setOpen] = useState(false);
  const { errors } = report;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2" aria-label="Data coverage">
        <Chip ok={report.market_snapshot !== null} label="Market snapshot" />
        <Chip ok={report.options_data !== null} label="Options data" />
        <Chip ok={report.citations.length > 0} label="Citations" />
      </div>

      {errors.length > 0 && (
        <div role="status" className="rounded-lg border border-amber/30 bg-amber/5 text-sm">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-amber focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
          >
            <AlertTriangle className="size-4 shrink-0" />
            <span className="font-medium">
              Partial report — {errors.length} source {errors.length === 1 ? "error" : "errors"}
            </span>
            <ChevronDown className={cn("ml-auto size-4 transition-transform", open && "rotate-180")} />
          </button>
          {open && (
            <ul className="space-y-1 border-t border-amber/20 px-4 py-3 font-mono text-xs text-foreground/80">
              {errors.map((e, i) => (
                <li key={i} className="break-words">
                  • {e}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
