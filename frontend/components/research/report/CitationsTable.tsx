"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SourceMixChart } from "@/components/charts/SourceMixChart";
import { ConfidenceBar } from "@/components/ConfidenceBar";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { hostnameOf } from "@/lib/format";
import type { Citation } from "@/types/research";

const PAGE = 50;

export function CitationsTable({ citations }: { citations: Citation[] }) {
  const [limit, setLimit] = useState(PAGE);
  if (citations.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No citations in this report.</p>;
  }

  return (
    <div className="space-y-5">
      <SourceMixChart citations={citations} />
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-12">#</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Metric</TableHead>
            <TableHead className="text-right">Value</TableHead>
            <TableHead className="w-44">Confidence</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {citations.slice(0, limit).map((c) => (
            <TableRow key={c.id}>
              <TableCell>
                <span className="rounded bg-primary/15 px-1.5 py-0.5 font-mono text-[11px] text-primary">
                  [{c.id}]
                </span>
              </TableCell>
              <TableCell className="max-w-[260px]">
                {c.source_url ? (
                <a
                  href={c.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={c.source_url}
                  className="inline-flex max-w-full items-center gap-1.5 truncate font-mono text-xs text-primary hover:underline"
                >
                  <span className="truncate">{hostnameOf(c.source_url)}</span>
                  <ExternalLink className="size-3 shrink-0" />
                </a>
                ) : (
                  <span className="text-xs text-muted-foreground">no URL</span>
                )}
              </TableCell>
              <TableCell>
                <Badge variant="muted">{c.source_type}</Badge>
              </TableCell>
              <TableCell className="text-muted-foreground">{c.metric}</TableCell>
              <TableCell className="text-right font-mono tabular-nums">{c.value}</TableCell>
              <TableCell>
                <ConfidenceBar value={c.confidence} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {citations.length > limit && (
        <div className="flex justify-center">
          <Button variant="outline" size="sm" onClick={() => setLimit((l) => l + PAGE)}>
            Show more ({citations.length - limit} remaining)
          </Button>
        </div>
      )}
    </div>
  );
}
