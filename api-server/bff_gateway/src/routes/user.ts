import { Router } from "express";
import { clerkClient } from "@clerk/express";

export const userRouter = Router();

userRouter.get("/profile", async (req, res, next) => {
  try {
    const tenant = req.tenant;
    if (!tenant) {
      res.status(403).json({ error: "no_active_organization", message: "No active organization" });
      return;
    }
    const user = await clerkClient.users.getUser(tenant.userId);
    res.json({
      user: {
        id: user.id,
        email: user.primaryEmailAddress?.emailAddress ?? null,
        first_name: user.firstName,
        last_name: user.lastName,
        image_url: user.imageUrl,
      },
      tenant: {
        id: tenant.tenantId,
        org_id: tenant.orgId,
        name: tenant.name,
        plan_tier: tenant.planTier,
        role: tenant.orgRole.replace(/^org:/, ""),
      },
    });
  } catch (err) {
    next(err);
  }
});
