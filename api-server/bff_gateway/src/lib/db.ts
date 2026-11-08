import { Pool } from "pg";
import { env } from "../config";

export const pool = new Pool({
  connectionString: env.NEON_DATABASE_URL,
  max: 10,
  idleTimeoutMillis: 30_000,
  connectionTimeoutMillis: 10_000,
});

pool.on("error", (err: Error) => {
  // eslint-disable-next-line no-console
  console.error(JSON.stringify({ level: "error", msg: "pg pool error", error: err.message }));
});

export interface TenantRow {
  id: string;
  name: string;
  clerk_org_id: string;
  plan_tier: string;
}

export async function getOrCreateTenant(clerkOrgId: string, name: string): Promise<TenantRow> {
  const { rows } = await pool.query<TenantRow>(
    `INSERT INTO tenants (name, clerk_org_id)
     VALUES ($1, $2)
     ON CONFLICT (clerk_org_id) DO UPDATE SET clerk_org_id = EXCLUDED.clerk_org_id
     RETURNING id, name, clerk_org_id, plan_tier`,
    [name, clerkOrgId],
  );
  const row = rows[0];
  if (!row) throw new Error("tenant upsert returned no row");
  return row;
}

export async function pingDb(): Promise<boolean> {
  try {
    await pool.query("SELECT 1");
    return true;
  } catch {
    return false;
  }
}
