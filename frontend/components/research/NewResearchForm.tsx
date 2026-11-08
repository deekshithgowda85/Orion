"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Rocket, Sparkles, Zap } from "lucide-react";
import { TickerInput } from "@/components/TickerInput";
import { WorkflowSelector } from "@/components/research/WorkflowSelector";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSubmitResearch } from "@/hooks/useSubmitResearch";
import { Input } from "@/components/ui/input";
import { EXAMPLE_PROMPTS, PRIORITY_LABELS, normalizeQuarter } from "@/lib/workflows";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui";
import type { Priority, WorkflowType } from "@/types/research";

const MAX_QUERY = 1000;

export function NewResearchForm() {
  const router = useRouter();
  const submit = useSubmitResearch();
  const defaultWorkflow = useUIStore((s) => s.defaultWorkflow);
  const defaultPriority = useUIStore((s) => s.defaultPriority);

  const [ticker, setTicker] = useState("");
  const [tickerValid, setTickerValid] = useState(false);
  const [quarter, setQuarter] = useState("");
  const [query, setQuery] = useState("");
  const [workflow, setWorkflow] = useState<WorkflowType>("deep_audit");
  const [priority, setPriority] = useState<Priority>("standard");

  useEffect(() => {
    setWorkflow(defaultWorkflow);
    setPriority(defaultPriority);
  }, [defaultWorkflow, defaultPriority]);

  const queryValid = query.trim().length >= 10;
  const quarterNormalized = quarter.trim() === "" ? undefined : (normalizeQuarter(quarter) ?? null);
  const quarterValid = quarterNormalized !== null;
  const canSubmit = tickerValid && queryValid && quarterValid && !submit.isPending;

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!canSubmit) return;
    submit.mutate(
      {
        ticker,
        ...(quarterNormalized ? { quarter: quarterNormalized } : {}),
        query: query.trim(),
        workflow_type: workflow,
        priority,
      },
      { onSuccess: (data) => router.push(`/research/${data.run_id}`) },
    );
  };

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Target</CardTitle>
          <CardDescription>What should the agents investigate?</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap gap-4">
            <div className="w-full space-y-1.5 sm:w-[220px]">
              <Label htmlFor="ticker">Ticker</Label>
              <TickerInput
                id="ticker"
                value={ticker}
                onChange={setTicker}
                onValidityChange={setTickerValid}
                disabled={submit.isPending}
                autoFocus
              />
            </div>
            <div className="w-full space-y-1.5 sm:w-[200px]">
              <Label htmlFor="quarter">
                Quarter <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id="quarter"
                value={quarter}
                onChange={(e) => setQuarter(e.target.value)}
                placeholder="2025Q3"
                className="font-mono"
                disabled={submit.isPending}
                aria-invalid={!quarterValid}
              />
              {!quarterValid && (
                <p className="text-xs text-amber">Use a format like 2025Q3 or Q3 2025.</p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="query">Research query</Label>
              <span
                className={cn(
                  "font-mono text-[11px]",
                  query.length > MAX_QUERY * 0.9 ? "text-amber" : "text-muted-foreground",
                )}
              >
                {query.length}/{MAX_QUERY}
              </span>
            </div>
            <Textarea
              id="query"
              value={query}
              onChange={(e) => setQuery(e.target.value.slice(0, MAX_QUERY))}
              placeholder="Describe the question, thesis or risk you want investigated…"
              rows={5}
              disabled={submit.isPending}
            />
            {query.length > 0 && !queryValid && (
              <p className="text-xs text-amber">Add a little more detail (at least 10 characters).</p>
            )}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Sparkles className="size-3" /> Try:
              </span>
              {EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => setQuery(prompt)}
                  disabled={submit.isPending}
                  className="max-w-full truncate rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                  title={prompt}
                >
                  {prompt.length > 54 ? `${prompt.slice(0, 54)}…` : prompt}
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Workflow</CardTitle>
          <CardDescription>Pick how deep the agents should go.</CardDescription>
        </CardHeader>
        <CardContent>
          <WorkflowSelector value={workflow} onChange={setWorkflow} disabled={submit.isPending} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Priority</CardTitle>
          <CardDescription>High-priority runs jump the queue.</CardDescription>
        </CardHeader>
        <CardContent>
          <div
            role="radiogroup"
            aria-label="Priority"
            className="inline-flex rounded-lg border border-border bg-surface p-1"
          >
            {(["standard", "high"] as const).map((p) => {
              const selected = priority === p;
              return (
                <button
                  key={p}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  disabled={submit.isPending}
                  onClick={() => setPriority(p)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                    selected
                      ? p === "high"
                        ? "bg-amber/15 text-amber"
                        : "bg-primary/15 text-primary"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {p === "high" && <Zap className="size-3.5" />}
                  {PRIORITY_LABELS[p]}
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {submit.isError && (
        <p
          role="alert"
          className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {submit.error.message}
        </p>
      )}

      <div className="flex items-center justify-end gap-3">
        <Button type="button" variant="ghost" onClick={() => router.back()} disabled={submit.isPending}>
          Cancel
        </Button>
        <Button type="submit" size="lg" disabled={!canSubmit}>
          {submit.isPending ? <Loader2 className="animate-spin" /> : <Rocket />}
          {submit.isPending ? "Submitting…" : "Launch research"}
        </Button>
      </div>
    </form>
  );
}
