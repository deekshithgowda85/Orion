import type { NextFunction, Request, Response } from "express";
import { clerkClient, getAuth } from "@clerk/express";
import { getOrCreateTenant } from "../lib/db";
import { redis, withRedisTimeout } from "../lib/redis";

export interface TenantContext {
  tenantId: string;
  orgId: string;
  name: string;
  planTier: string;
  userId: string;
  orgRole: string;
}

const TENANT_TTL_SECONDS = 300;

interface CachedTenant {
  tenantId: string;
  name: string;
  planTier: string;
}

export async function resolveTenant(orgId: string): Promise<CachedTenant> {
  const key = `tenant:meta:${orgId}`;
  try {
    const cached = await withRedisTimeout(redis.get(key));
    if (cached) return JSON.parse(cached) as CachedTenant;
  } catch {
    // Redis unavailable: fall through to the database.
  }

  let name = orgId;
  try {
    const org = await clerkClient.organizations.getOrganization({ organizationId: orgId });
    name = org.name;
  } catch {
    // Org name is cosmetic; tenant creation must not fail because of it.
  }
  const row = await getOrCreateTenant(orgId, name);
  const value: CachedTenant = { tenantId: row.id, name: row.name, planTier: row.plan_tier };
  try {
    await withRedisTimeout(redis.set(key, JSON.stringify(value), "EX", TENANT_TTL_SECONDS));
  } catch {
    // Cache write failures are non-fatal.
  }
  return value;
}

/** Resolves the tenant from the Clerk org and injects X-Tenant-ID / X-User-ID. */
export async function tenantMiddleware(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const auth = getAuth(req);
    if (!auth.userId) {
      res.status(401).json({ error: "unauthorized", message: "Authentication required" });
      return;
    }
    if (!auth.orgId) {
      res.status(403).json({
        error: "no_active_organization",
        message: "Select or create an organization to use this API",
      });
      return;
    }

    const tenant = await resolveTenant(auth.orgId);
    req.tenant = {
      tenantId: tenant.tenantId,
      orgId: auth.orgId,
      name: tenant.name,
      planTier: tenant.planTier,
      userId: auth.userId,
      orgRole: auth.orgRole ?? "org:member",
    };

    // Overwrite any client-supplied values so they can never be spoofed.
    req.headers["x-tenant-id"] = tenant.tenantId;
    req.headers["x-user-id"] = auth.userId;

    // FastAPI verifies the Clerk JWT itself; make sure it receives one even for cookie-based sessions.
    if (!req.headers.authorization) {
      const token = await auth.getToken();
      if (token) req.headers.authorization = `Bearer ${token}`;
    }
    next();
  } catch (err) {
    next(err);
  }
}
