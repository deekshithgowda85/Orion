"use client";

import { useEffect, useState } from "react";
import { format } from "date-fns";
import { CalendarClock, Trash2 } from "lucide-react";
import { NewScheduleDialog } from "@/components/workflows/NewScheduleDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { nextRunDate } from "@/lib/cron";
import { WORKFLOW_LABELS } from "@/lib/workflows";
import { useSchedulesStore } from "@/store/schedules";

export function SchedulesSection() {
  const schedules = useSchedulesStore((s) => s.schedules);
  const toggleSchedule = useSchedulesStore((s) => s.toggleSchedule);
  const removeSchedule = useSchedulesStore((s) => s.removeSchedule);

  // Schedules live in localStorage — render them only after hydration.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const rows = mounted ? schedules : [];

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle>Scheduled workflows</CardTitle>
          <CardDescription>Recurring runs, evaluated in your local timezone.</CardDescription>
        </div>
        <NewScheduleDialog />
      </CardHeader>
      <CardContent className="px-2 pb-3">
        {rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-3 py-10 text-center">
            <CalendarClock className="size-8 text-muted-foreground/60" />
            <p className="text-sm text-muted-foreground">
              No schedules yet. Create one to run a workflow automatically.
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Ticker</TableHead>
                <TableHead>Workflow</TableHead>
                <TableHead>Cron</TableHead>
                <TableHead>Next run</TableHead>
                <TableHead className="text-center">Enabled</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((s) => {
                const next = s.enabled ? nextRunDate(s.cron) : null;
                return (
                  <TableRow key={s.id}>
                    <TableCell className="font-mono text-sm font-semibold text-primary">
                      {s.ticker}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {WORKFLOW_LABELS[s.workflow_type]}
                    </TableCell>
                    <TableCell>
                      <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-xs">
                        {s.cron}
                      </code>
                    </TableCell>
                    <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                      {next ? format(next, "EEE, MMM d · HH:mm") : s.enabled ? "—" : "Paused"}
                    </TableCell>
                    <TableCell className="text-center">
                      <Switch
                        checked={s.enabled}
                        onCheckedChange={(checked) => toggleSchedule(s.id, checked)}
                        aria-label={`${s.enabled ? "Disable" : "Enable"} ${s.ticker} schedule`}
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => removeSchedule(s.id)}
                        aria-label={`Delete ${s.ticker} schedule`}
                        className="text-muted-foreground hover:text-danger"
                      >
                        <Trash2 />
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
