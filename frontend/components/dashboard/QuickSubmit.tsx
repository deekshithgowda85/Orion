"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Rocket } from "lucide-react";
import { TickerInput } from "@/components/TickerInput";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSubmitResearch } from "@/hooks/useSubmitResearch";
import { WORKFLOW_OPTIONS } from "@/lib/workflows";
import { useUIStore } from "@/store/ui";
import type { WorkflowType } from "@/types/research";

export function QuickSubmit() {
  const router = useRouter();
  const submit = useSubmitResearch();
  const defaultWorkflow = useUIStore((s) => s.defaultWorkflow);
  const defaultPriority = useUIStore((s) => s.defaultPriority);

  const [ticker, setTicker] = useState("");
  const [tickerValid, setTickerValid] = useState(false);
  const [query, setQuery] = useState("");
  const [workflow, setWorkflow] = useState<WorkflowType>("deep_audit");

  // Apply persisted defaults after hydration (avoids server/client mismatch).
  useEffect(() => {
    setWorkflow(defaultWorkflow);
  }, [defaultWorkflow]);

  const canSubmit = tickerValid && query.trim().length >= 3 && !submit.isPending;

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!canSubmit) return;
    submit.mutate(
      { ticker, query: query.trim(), workflow_type: workflow, priority: defaultPriority },
      { onSuccess: (data) => router.push(`/research/${data.run_id}`) },
    );
  };

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>Quick submit</CardTitle>
        <CardDescription>Launch a research run without leaving the overview.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-[140px_1fr]">
            <div className="space-y-1.5">
              <Label htmlFor="qs-ticker">Ticker</Label>
              <TickerInput
                id="qs-ticker"
                value={ticker}
                onChange={setTicker}
                onValidityChange={setTickerValid}
                disabled={submit.isPending}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="qs-query">Query</Label>
              <Input
                id="qs-query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. Assess margin sustainability vs consensus"
                disabled={submit.isPending}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="qs-workflow">Workflow type</Label>
            <select
              id="qs-workflow"
              value={workflow}
              onChange={(e) => setWorkflow(e.target.value as WorkflowType)}
              disabled={submit.isPending}
              className="flex h-9 w-full rounded-md border border-border bg-input px-3 text-sm focus-visible:border-primary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
            >
              {WORKFLOW_OPTIONS.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.label} — {w.duration}
                </option>
              ))}
            </select>
          </div>

          {submit.isError && (
            <p role="alert" className="text-sm text-danger">
              {submit.error.message}
            </p>
          )}

          <Button type="submit" disabled={!canSubmit} className="w-full">
            {submit.isPending ? <Loader2 className="animate-spin" /> : <Rocket />}
            {submit.isPending ? "Submitting…" : "Run research"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
