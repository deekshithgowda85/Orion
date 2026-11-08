"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

interface RunIdDisplayProps {
  runId: string;
  /** Show only the first N characters (full id is still copied). */
  truncate?: number;
  className?: string;
}

/** Monospace run id with a copy-to-clipboard button. */
export function RunIdDisplay({ runId, truncate, className }: RunIdDisplayProps) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    },
    [],
  );

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(runId);
      setCopied(true);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — ignore */
    }
  };

  const shown = truncate && runId.length > truncate ? `${runId.slice(0, truncate)}…` : runId;

  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 font-mono text-xs text-foreground",
        className,
      )}
    >
      <span className="truncate" title={runId}>
        {shown}
      </span>
      <button
        type="button"
        onClick={copy}
        aria-label={copied ? "Run ID copied" : "Copy run ID"}
        className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
      >
        {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
      </button>
    </span>
  );
}
