"use client";

import { Fragment, type ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatPercent, hostnameOf } from "@/lib/format";
import type { Citation } from "@/types/research";

interface CitationBadgeProps {
  index: number;
  citation?: Citation;
}

/** Inline [n] marker; hover shows the backing source, metric and confidence. */
export function CitationBadge({ index, citation }: CitationBadgeProps) {
  const marker = (
    <sup className="mx-0.5 inline-flex cursor-help items-center rounded bg-primary/15 px-1 font-mono text-[10px] font-medium text-primary transition-colors hover:bg-primary/30">
      [{index}]
    </sup>
  );

  if (!citation) return marker;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{marker}</TooltipTrigger>
      <TooltipContent className="space-y-1.5">
        <div className="flex items-center justify-between gap-4">
          <span className="font-medium">{citation.metric}</span>
          <span className="font-mono text-primary">{citation.value}</span>
        </div>
        <div className="flex items-center gap-1 text-muted-foreground">
          <ExternalLink className="size-3 shrink-0" />
          <span className="truncate font-mono">{hostnameOf(citation.source_url)}</span>
        </div>
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span className="uppercase tracking-wider">{citation.source_type}</span>
          <span className="font-mono">conf {formatPercent(citation.confidence)}</span>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

/** Splits text on [n] markers and swaps each for a <CitationBadge/>. */
export function renderWithCitations(text: string, citations: Citation[]): ReactNode[] {
  const byId = new Map<number, Citation>(citations.map((c) => [c.id, c]));
  const parts = text.split(/\[(\d+)\]/g);

  return parts.map((part, i) => {
    // Odd indexes are the captured citation numbers.
    if (i % 2 === 1) {
      const n = Number(part);
      return <CitationBadge key={`c-${i}`} index={n} citation={byId.get(n)} />;
    }
    return <Fragment key={`t-${i}`}>{part}</Fragment>;
  });
}
