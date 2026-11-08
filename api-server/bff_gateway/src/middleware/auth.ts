import type { NextFunction, Request, Response } from "express";
import { getAuth } from "@clerk/express";

/**
 * API-friendly replacement for Clerk's requireAuth(), which redirects to a
 * sign-in page. For a JSON gateway we want a plain 401 instead.
 * clerkMiddleware() must run before this (see app.ts).
 */
export function requireApiAuth(req: Request, res: Response, next: NextFunction): void {
  const auth = getAuth(req);
  if (!auth.userId) {
    res.status(401).json({ error: "unauthorized", message: "Authentication required" });
    return;
  }
  next();
}
