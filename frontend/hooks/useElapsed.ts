"use client";

import { useEffect, useState } from "react";
import { safeParseDate } from "@/lib/format";

/**
 * Live elapsed-seconds counter. Ticks every second while `running`; once the run
 * ends it freezes at (endedAt - startedAt).
 */
export function useElapsed(
  startedAt: string | null | undefined,
  endedAt: string | null | undefined,
  running: boolean,
): number {
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);

  const start = safeParseDate(startedAt);
  if (!start) return 0;
  const end = !running ? safeParseDate(endedAt) : null;
  const endMs = end ? end.getTime() : now;
  return Math.max(0, (endMs - start.getTime()) / 1000);
}
