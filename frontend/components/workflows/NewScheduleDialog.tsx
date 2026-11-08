"use client";

import { useMemo, useState } from "react";
import { format } from "date-fns";
import { CalendarClock, Plus } from "lucide-react";
import { TickerInput } from "@/components/TickerInput";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CRON_PRESETS, nextRunDate } from "@/lib/cron";
import { WORKFLOW_OPTIONS } from "@/lib/workflows";
import { useSchedulesStore } from "@/store/schedules";
import type { WorkflowType } from "@/types/research";

export function NewScheduleDialog() {
  const addSchedule = useSchedulesStore((s) => s.addSchedule);

  const [open, setOpen] = useState(false);
  const [ticker, setTicker] = useState("");
  const [tickerValid, setTickerValid] = useState(false);
  const [workflow, setWorkflow] = useState<WorkflowType>("daily_scan");
  const [cron, setCron] = useState("0 9 * * 1-5");

  const next = useMemo(() => nextRunDate(cron), [cron]);
  const canSave = tickerValid && next !== null;

  const reset = () => {
    setTicker("");
    setWorkflow("daily_scan");
    setCron("0 9 * * 1-5");
  };

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!canSave) return;
    addSchedule({ ticker, workflow_type: workflow, cron: cron.trim() });
    setOpen(false);
    reset();
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus />
          New Schedule
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>New scheduled workflow</DialogTitle>
            <DialogDescription>
              Run a workflow automatically on a cron schedule (your local timezone).
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="sch-ticker">Ticker</Label>
              <TickerInput
                id="sch-ticker"
                value={ticker}
                onChange={setTicker}
                onValidityChange={setTickerValid}
                autoFocus
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="sch-workflow">Workflow type</Label>
              <select
                id="sch-workflow"
                value={workflow}
                onChange={(e) => setWorkflow(e.target.value as WorkflowType)}
                className="flex h-9 w-full rounded-md border border-border bg-input px-3 text-sm focus-visible:border-primary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
              >
                {WORKFLOW_OPTIONS.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.label} — {w.duration}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="sch-cron">Cron expression</Label>
              <Input
                id="sch-cron"
                value={cron}
                onChange={(e) => setCron(e.target.value)}
                placeholder="0 9 * * 1-5"
                spellCheck={false}
                aria-invalid={next === null}
                className="font-mono"
              />
              <div className="flex flex-wrap gap-2 pt-1">
                {CRON_PRESETS.map((p) => (
                  <button
                    key={p.cron}
                    type="button"
                    onClick={() => setCron(p.cron)}
                    className="rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              {next ? (
                <p className="flex items-center gap-1.5 pt-1 text-xs text-muted-foreground">
                  <CalendarClock className="size-3.5 text-primary" />
                  Next run:{" "}
                  <span className="font-mono text-foreground">{format(next, "EEE, MMM d · HH:mm")}</span>
                </p>
              ) : (
                <p className="pt-1 text-xs text-danger">
                  Invalid cron expression. Use 5 fields: minute hour day month weekday.
                </p>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSave}>
              Create schedule
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
