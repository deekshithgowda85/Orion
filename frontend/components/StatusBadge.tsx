import { CheckCircle2, Clock, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { RunStatusValue } from "@/types/research";

interface StatusBadgeProps {
  status: RunStatusValue;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  switch (status) {
    case "queued":
      return (
        <Badge variant="muted" className={className}>
          <Clock className="size-3" />
          Queued
        </Badge>
      );
    case "running":
      return (
        <Badge variant="cyan" className={className}>
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-50" />
            <span className="relative inline-flex size-2 rounded-full bg-primary" />
          </span>
          Running
        </Badge>
      );
    case "completed":
      return (
        <Badge variant="success" className={className}>
          <CheckCircle2 className="size-3" />
          Completed
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="danger" className={cn(className)}>
          <XCircle className="size-3" />
          Failed
        </Badge>
      );
  }
}
