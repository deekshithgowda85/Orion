import { parseExpression } from "cron-parser";

export interface CronPreset {
  label: string;
  cron: string;
}

export const CRON_PRESETS: readonly CronPreset[] = [
  { label: "Weekdays 09:00", cron: "0 9 * * 1-5" },
  { label: "After close 16:30", cron: "30 16 * * 1-5" },
  { label: "Daily 06:00", cron: "0 6 * * *" },
  { label: "Hourly", cron: "0 * * * *" },
];

/** Next fire time in the browser's local timezone, or null if the expression is invalid. */
export function nextRunDate(cron: string): Date | null {
  const trimmed = cron.trim();
  const fields = trimmed.split(/\s+/);
  if (fields.length < 5 || fields.length > 6) return null;
  try {
    return parseExpression(trimmed).next().toDate();
  } catch {
    return null;
  }
}

export function isValidCron(cron: string): boolean {
  return nextRunDate(cron) !== null;
}
