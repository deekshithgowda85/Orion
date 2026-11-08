"use client";

import { useEffect, useState } from "react";
import { OrgSwitcher } from "@/components/auth/OrgSwitcher";
import { RotateCcw, Zap } from "lucide-react";
import { WorkflowSelector } from "@/components/research/WorkflowSelector";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PRIORITY_LABELS } from "@/lib/workflows";
import { cn } from "@/lib/utils";
import { useSchedulesStore } from "@/store/schedules";
import { useUIStore } from "@/store/ui";

export function SettingsPanel() {
  const defaultWorkflow = useUIStore((s) => s.defaultWorkflow);
  const defaultPriority = useUIStore((s) => s.defaultPriority);
  const setDefaultWorkflow = useUIStore((s) => s.setDefaultWorkflow);
  const setDefaultPriority = useUIStore((s) => s.setDefaultPriority);

  // Persisted values only exist client-side; wait for hydration before showing them.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [resetDone, setResetDone] = useState(false);
  const resetLocalData = () => {
    useUIStore.setState({
      defaultWorkflow: "deep_audit",
      defaultPriority: "standard",
      sidebarCollapsed: false,
    });
    useSchedulesStore.setState({ schedules: [] });
    setResetDone(true);
    setTimeout(() => setResetDone(false), 2000);
  };

  return (
    <div className="max-w-4xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Organization</CardTitle>
          <CardDescription>
            Runs, reports and schedules are scoped to the active organization. Switch organizations
            to see a different workspace.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="max-w-xs">
            <OrgSwitcher />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Research defaults</CardTitle>
          <CardDescription>
            Pre-selected on the New Research page and the overview quick-submit. Stored in this
            browser.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Default workflow
            </p>
            <WorkflowSelector
              value={mounted ? defaultWorkflow : "deep_audit"}
              onChange={setDefaultWorkflow}
            />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Default priority
            </p>
            <div
              role="radiogroup"
              aria-label="Default priority"
              className="inline-flex rounded-lg border border-border bg-surface p-1"
            >
              {(["standard", "high"] as const).map((p) => {
                const selected = (mounted ? defaultPriority : "standard") === p;
                return (
                  <button
                    key={p}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setDefaultPriority(p)}
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
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Connection</CardTitle>
          <CardDescription>
            All API traffic goes through this app&apos;s <code className="font-mono">/api/*</code>{" "}
            proxy to the BFF gateway configured by <code className="font-mono">BFF_URL</code>.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div className="rounded-lg border border-border bg-surface px-4 py-3">
              <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">
                Live updates
              </dt>
              <dd className="mt-1 font-mono text-primary">GET /api/research/&#123;run_id&#125;/stream</dd>
            </div>
            <div className="rounded-lg border border-border bg-surface px-4 py-3">
              <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">
                Status polling
              </dt>
              <dd className="mt-1 font-mono text-primary">every 5s while running</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Local data</CardTitle>
          <CardDescription>
            Preferences and schedules are kept in this browser&apos;s local storage.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={resetLocalData}>
            <RotateCcw />
            {resetDone ? "Reset complete" : "Reset local preferences & schedules"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
