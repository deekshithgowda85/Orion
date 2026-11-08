import { Loader2, WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ConnectionState } from "@/types/research";

const LABELS: Record<ConnectionState, string> = {
  idle: "Idle",
  connecting: "Connecting…",
  open: "Live",
  reconnecting: "Reconnecting…",
  disconnected: "Disconnected",
  closed: "Stream closed",
};

export function ConnectionPill({ state }: { state: ConnectionState }) {
  const tone =
    state === "open"
      ? "border-success/30 bg-success/10 text-success"
      : state === "disconnected"
        ? "border-amber/30 bg-amber/10 text-amber"
        : "border-border bg-muted text-muted-foreground";

  return (
    <span
      role="status"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        tone,
      )}
    >
      {state === "open" && (
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-70" />
          <span className="relative inline-flex size-2 rounded-full bg-success" />
        </span>
      )}
      {(state === "connecting" || state === "reconnecting") && (
        <Loader2 className="size-3 animate-spin" />
      )}
      {state === "disconnected" && <WifiOff className="size-3" />}
      {LABELS[state]}
    </span>
  );
}
