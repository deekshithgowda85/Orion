"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { JsonValue } from "@/types/research";

interface JsonViewerProps {
  data: JsonValue;
  /** How many levels start expanded. */
  defaultExpandDepth?: number;
  className?: string;
}

/** Collapsible, syntax-highlighted JSON tree. */
export function JsonViewer({ data, defaultExpandDepth = 1, className }: JsonViewerProps) {
  return (
    <div className={cn("font-mono text-xs leading-relaxed", className)}>
      <JsonNode value={data} depth={0} defaultExpandDepth={defaultExpandDepth} />
    </div>
  );
}

/** Large arrays/objects render this many children at a time so huge payloads stay responsive. */
const CHILD_PAGE = 100;

interface JsonNodeProps {
  name?: string;
  value: JsonValue;
  depth: number;
  defaultExpandDepth: number;
  isLast?: boolean;
}

function Primitive({ value }: { value: string | number | boolean | null }) {
  if (value === null) return <span className="text-muted-foreground">null</span>;
  if (typeof value === "string") return <span className="break-all text-primary">&quot;{value}&quot;</span>;
  if (typeof value === "number") return <span className="text-amber">{value}</span>;
  return <span className="text-primary">{String(value)}</span>;
}

function JsonNode({ name, value, depth, defaultExpandDepth, isLast = true }: JsonNodeProps) {
  const [open, setOpen] = useState(depth < defaultExpandDepth);
  const [limit, setLimit] = useState(CHILD_PAGE);
  const comma = isLast ? "" : ",";
  const keyLabel =
    name !== undefined ? (
      <>
        <span className="text-foreground/90">&quot;{name}&quot;</span>
        <span className="text-muted-foreground">: </span>
      </>
    ) : null;

  if (value === null || typeof value !== "object") {
    return (
      <div className="pl-4">
        {keyLabel}
        <Primitive value={value} />
        <span className="text-muted-foreground">{comma}</span>
      </div>
    );
  }

  const isArray = Array.isArray(value);
  const entries: [string, JsonValue][] = isArray
    ? value.map((v, i): [string, JsonValue] => [String(i), v])
    : Object.entries(value);
  const [openBracket, closeBracket] = isArray ? ["[", "]"] : ["{", "}"];

  if (entries.length === 0) {
    return (
      <div className="pl-4">
        {keyLabel}
        <span className="text-muted-foreground">
          {openBracket}
          {closeBracket}
          {comma}
        </span>
      </div>
    );
  }

  return (
    <div className="pl-4">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="-ml-4 inline-flex items-center gap-0.5 rounded text-left hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
      >
        <ChevronRight
          className={cn("size-3.5 text-muted-foreground transition-transform", open && "rotate-90")}
        />
        {keyLabel}
        <span className="text-muted-foreground">{openBracket}</span>
        {!open && (
          <span className="text-muted-foreground/70">
            {" "}
            {entries.length} {isArray ? "items" : "keys"} {closeBracket}
            {comma}
          </span>
        )}
      </button>
      {open && (
        <>
          {entries.slice(0, limit).map(([k, v], i) => (
            <JsonNode
              key={k}
              name={isArray ? undefined : k}
              value={v}
              depth={depth + 1}
              defaultExpandDepth={defaultExpandDepth}
              isLast={i === entries.length - 1}
            />
          ))}
          {entries.length > limit && (
            <button
              type="button"
              onClick={() => setLimit((l) => l + CHILD_PAGE)}
              className="pl-4 text-primary hover:underline"
            >
              … show {Math.min(CHILD_PAGE, entries.length - limit)} more ({entries.length - limit} hidden)
            </button>
          )}
          <div className="text-muted-foreground">
            {closeBracket}
            {comma}
          </div>
        </>
      )}
    </div>
  );
}
