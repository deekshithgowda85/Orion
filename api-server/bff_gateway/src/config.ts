import "dotenv/config";
import { z } from "zod";

const EnvSchema = z.object({
  PORT: z.coerce.number().int().positive().default(3001),
  FASTAPI_BASE_URL: z.string().url(),
  CLERK_SECRET_KEY: z.string().min(1),
  CLERK_PUBLISHABLE_KEY: z.string().min(1),
  REDIS_URL: z.string().url(),
  ALLOWED_ORIGINS: z.string().min(1),
  NEON_DATABASE_URL: z.string().min(1),
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
});

const parsed = EnvSchema.safeParse(process.env);
if (!parsed.success) {
  const fields = parsed.error.flatten().fieldErrors;
  // eslint-disable-next-line no-console
  console.error(
    "bff_gateway cannot start: invalid environment configuration.\n" +
      Object.entries(fields).map(([k, v]) => `  ${k}: ${(v ?? []).join(", ")}`).join("\n") +
      "\n  Copy .env.example to .env and fill the values.",
  );
  process.exit(1);
}

export const env = {
  ...parsed.data,
  allowedOrigins: parsed.data.ALLOWED_ORIGINS.split(",").map((s) => s.trim()).filter(Boolean),
};
