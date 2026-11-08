"use client";

import { useState } from "react";
import { Check, Copy, Download, Loader2 } from "lucide-react";
import { renderWithCitations } from "@/components/CitationBadge";
import { ConfidenceBar } from "@/components/ConfidenceBar";
import { JsonViewer } from "@/components/JsonViewer";
import { MetricCard } from "@/components/MetricCard";
import { CitationsTable } from "@/components/research/report/CitationsTable";
import { DataCoverage } from "@/components/research/report/DataCoverage";
import { TraceLogView } from "@/components/research/report/TraceLogView";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { downloadReportPdf } from "@/lib/api";
import { formatFullDateTime } from "@/lib/format";
import type { Citation, ResearchReport } from "@/types/research";

const COLLAPSE_AT = 3000;

function Paragraphs({ text, citations }: { text: string; citations: Citation[] }) {
  const blocks = text.split(/\n{2,}/).filter((b) => b.trim().length > 0);
  if (blocks.length === 0) {
    return <p className="text-sm italic text-muted-foreground">No content was generated for this part.</p>;
  }
  return (
    <div className="space-y-3 break-words text-sm leading-relaxed text-foreground/90">
      {blocks.map((block, i) => (
        <p key={i}>{renderWithCitations(block, citations)}</p>
      ))}
    </div>
  );
}

/** Very long sections start collapsed so a 100-page report doesn't render as one wall of text. */
function SectionBody({ text, citations }: { text: string; citations: Citation[] }) {
  const [expanded, setExpanded] = useState(false);
  const long = text.length > COLLAPSE_AT;
  const shown = long && !expanded ? `${text.slice(0, COLLAPSE_AT)}…` : text;
  return (
    <>
      <Paragraphs text={shown} citations={citations} />
      {long && (
        <Button variant="ghost" size="sm" className="mt-3" onClick={() => setExpanded((e) => !e)}>
          {expanded ? "Show less" : `Show all (${Math.ceil(text.length / 1000)}k characters)`}
        </Button>
      )}
    </>
  );
}

export function ReportViewer({ report }: { report: ResearchReport }) {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const download = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadReportPdf(report.run_id, report.ticker);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  };

  const copyRaw = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(report.raw_data, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-4">
        <div>
          <CardTitle className="text-xl">
            Research report · <span className="font-mono text-primary">{report.ticker}</span>
          </CardTitle>
          <CardDescription>
            Generated {formatFullDateTime(report.generated_at)}
            {report.quarter ? ` · ${report.quarter}` : ""}
          </CardDescription>
        </div>
        <div className="flex items-center gap-4">
          <div className="w-44">
            <p className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">
              Overall confidence
            </p>
            <ConfidenceBar value={report.confidence_score} />
          </div>
          <Button variant="outline" size="sm" onClick={download} disabled={downloading}>
            {downloading ? <Loader2 className="animate-spin" /> : <Download />}
            PDF
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {downloadError && (
          <p role="alert" className="mb-3 text-sm text-danger">
            {downloadError}
          </p>
        )}
        <Tabs defaultValue="summary">
          <TabsList className="h-auto flex-wrap">
            <TabsTrigger value="summary">Executive Summary</TabsTrigger>
            <TabsTrigger value="sections">Sections ({report.sections.length})</TabsTrigger>
            <TabsTrigger value="citations">Citations ({report.citations.length})</TabsTrigger>
            <TabsTrigger value="raw">Raw Data</TabsTrigger>
            <TabsTrigger value="trace">Trace Log ({report.trace_log.length})</TabsTrigger>
          </TabsList>

          <TabsContent value="summary" className="space-y-5">
            <DataCoverage report={report} />
            {report.key_metrics.length > 0 && (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {report.key_metrics.map((m) => (
                  <MetricCard
                    key={m.label}
                    label={m.label}
                    value={m.value}
                    missing={m.missing}
                    changePct={m.change_pct}
                    source={m.source}
                  />
                ))}
              </div>
            )}
            {report.executive_summary.trim() ? (
              <Paragraphs text={report.executive_summary} citations={report.citations} />
            ) : (
              <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                The backend returned no executive summary for this run.
              </p>
            )}
          </TabsContent>

          <TabsContent value="sections" className="space-y-4">
            {report.sections.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">No sections in this report.</p>
            )}
            {report.sections.map((section) => (
              <section
                key={section.id}
                className="rounded-xl border border-border bg-surface p-5"
              >
                <h3 className="mb-3 font-heading text-lg font-semibold">{section.title}</h3>
                <SectionBody text={section.content} citations={report.citations} />
              </section>
            ))}
          </TabsContent>

          <TabsContent value="citations">
            <CitationsTable citations={report.citations} />
          </TabsContent>

          <TabsContent value="raw">
            <div className="mb-3 flex justify-end">
              <Button size="sm" variant="outline" onClick={copyRaw}>
                {copied ? <Check className="text-success" /> : <Copy />}
                {copied ? "Copied" : "Copy JSON"}
              </Button>
            </div>
            {Object.keys(report.raw_data).length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No raw data was attached to this report.
              </p>
            ) : (
              <div className="max-h-[560px] overflow-auto rounded-lg border border-border bg-surface p-4">
                <JsonViewer data={report.raw_data} defaultExpandDepth={1} />
              </div>
            )}
          </TabsContent>

          <TabsContent value="trace">
            <TraceLogView trace={report.trace_log} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
