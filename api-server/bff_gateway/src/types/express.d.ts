import type { TenantContext } from "../middleware/tenant";

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      tenant?: TenantContext;
      requestId?: string;
    }
  }
}

export {};
