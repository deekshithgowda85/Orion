"use client";

import { useEffect } from "react";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { TICKER_PATTERN } from "@/lib/workflows";
import { cn } from "@/lib/utils";

type ValidationState = "idle" | "checking" | "valid" | "invalid";

interface TickerInputProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  onValidityChange?: (valid: boolean) => void;
  disabled?: boolean;
  autoFocus?: boolean;
  className?: string;
}

/** Ticker field with debounced (300ms) format validation. Input is upper-cased as you type. */
export function TickerInput({
  id,
  value,
  onChange,
  onValidityChange,
  disabled,
  autoFocus,
  className,
}: TickerInputProps) {
  const debounced = useDebouncedValue(value, 300);

  const state: ValidationState =
    value.length === 0
      ? "idle"
      : value !== debounced
        ? "checking"
        : TICKER_PATTERN.test(value)
          ? "valid"
          : "invalid";

  useEffect(() => {
    onValidityChange?.(state === "valid");
  }, [state, onValidityChange]);

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="relative">
        <Input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value.toUpperCase().replace(/[^A-Z.\-]/g, "").slice(0, 8))}
          placeholder="AAPL"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          autoFocus={autoFocus}
          disabled={disabled}
          aria-invalid={state === "invalid"}
          className={cn(
            "pr-9 font-mono uppercase tracking-wider",
            state === "invalid" && "border-danger/60 focus-visible:ring-danger/30",
            state === "valid" && "border-success/40",
          )}
        />
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2">
          {state === "checking" && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
          {state === "valid" && <CheckCircle2 className="size-4 text-success" />}
          {state === "invalid" && <AlertCircle className="size-4 text-danger" />}
        </span>
      </div>
      {state === "invalid" && (
        <p className="text-xs text-danger">
          Use 1–5 letters, optionally with a class suffix (e.g. AAPL, BRK.B).
        </p>
      )}
    </div>
  );
}
