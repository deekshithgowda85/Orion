"use client";

import { Check, Clock } from "lucide-react";
import { WORKFLOW_OPTIONS } from "@/lib/workflows";
import { cn } from "@/lib/utils";
import type { WorkflowType } from "@/types/research";

interface WorkflowSelectorProps {
  value: WorkflowType;
  onChange: (value: WorkflowType) => void;
  disabled?: boolean;
}

/** Radio-group of workflow cards: icon, description, estimated duration. */
export function WorkflowSelector({ value, onChange, disabled }: WorkflowSelectorProps) {
  return (
    <div role="radiogroup" aria-label="Workflow type" className="grid gap-3 md:grid-cols-3">
      {WORKFLOW_OPTIONS.map((option) => {
        const selected = option.id === value;
        const Icon = option.icon;
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(option.id)}
            className={cn(
              "group relative flex flex-col items-start gap-3 rounded-xl border p-4 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 disabled:opacity-60",
              selected
                ? "border-primary/60 bg-primary/10 shadow-[0_0_0_1px_rgb(99_102_241/0.4),0_8px_30px_-12px_rgb(99_102_241/0.5)]"
                : "border-border bg-card hover:border-primary/30 hover:bg-card-elevated",
            )}
          >
            <div className="flex w-full items-start justify-between">
              <div
                className={cn(
                  "flex size-10 items-center justify-center rounded-lg ring-1",
                  selected
                    ? "bg-primary/20 text-primary ring-primary/40"
                    : "bg-muted text-muted-foreground ring-border",
                )}
              >
                <Icon className="size-5" />
              </div>
              {selected && (
                <span className="flex size-5 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  <Check className="size-3" />
                </span>
              )}
            </div>
            <div>
              <p className="font-heading text-base font-semibold">{option.label}</p>
              <p className="mt-1 text-sm leading-snug text-muted-foreground">{option.description}</p>
            </div>
            <span className="mt-auto inline-flex items-center gap-1.5 rounded-md bg-surface px-2 py-1 font-mono text-xs text-primary">
              <Clock className="size-3" />
              {option.duration}
            </span>
          </button>
        );
      })}
    </div>
  );
}
