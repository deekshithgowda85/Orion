import { z } from "zod";

export const WORKFLOW_TYPES = [
  "full_research",
  "earnings_analysis",
  "competitor_comparison",
  "sec_filing_digest",
  "technical_snapshot",
] as const;

export const ResearchSubmitSchema = z
  .object({
    ticker: z
      .string()
      .trim()
      .regex(/^[A-Za-z0-9.\-]{1,10}$/, "ticker must be 1-10 characters: letters, digits, '.' or '-'")
      .transform((v) => v.toUpperCase()),
    quarter: z
      .string()
      .trim()
      .regex(/^[A-Za-z0-9 _\-]{1,16}$/, "quarter must be 1-16 characters, e.g. 2025Q3")
      .optional(),
    query: z.string().trim().min(3, "query must be at least 3 characters").max(2000),
    workflow_type: z.enum(WORKFLOW_TYPES).default("full_research"),
    priority: z.enum(["low", "normal", "high"]).default("normal"),
  })
  .strict();

export type ResearchSubmit = z.infer<typeof ResearchSubmitSchema>;
