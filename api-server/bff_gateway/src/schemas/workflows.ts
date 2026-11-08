import { z } from "zod";
import { WORKFLOW_TYPES } from "./research";

const CRON_FIELD = /^[0-9A-Za-z*/,\-?]+$/;

export const WorkflowScheduleSchema = z
  .object({
    ticker: z
      .string()
      .trim()
      .regex(/^[A-Za-z0-9.\-]{1,10}$/, "ticker must be 1-10 characters: letters, digits, '.' or '-'")
      .transform((v) => v.toUpperCase()),
    workflow_type: z.enum(WORKFLOW_TYPES),
    cron_expr: z
      .string()
      .trim()
      .refine((v) => {
        const parts = v.split(/\s+/);
        return parts.length === 5 && parts.every((p) => CRON_FIELD.test(p));
      }, "cron_expr must be a valid 5-field cron expression, e.g. '0 9 * * 1-5'"),
    quarter: z
      .string()
      .trim()
      .regex(/^[A-Za-z0-9 _\-]{1,16}$/, "quarter must be 1-16 characters, e.g. 2025Q3")
      .optional(),
    query: z.string().trim().max(2000).optional(),
  })
  .strict();

export type WorkflowSchedule = z.infer<typeof WorkflowScheduleSchema>;
