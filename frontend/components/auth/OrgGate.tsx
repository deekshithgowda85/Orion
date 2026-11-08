"use client";

import { OrganizationList, useAuth } from "@clerk/nextjs";
import { MOCK_MODE } from "@/lib/mock-mode";
import { Skeleton } from "@/components/ui/skeleton";

function ClerkOrgGate({ children }: { children: React.ReactNode }) {
  const { isLoaded, orgId } = useAuth();

  if (!isLoaded) return <Skeleton className="h-64 w-full rounded-xl" />;

  if (!orgId) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-16 text-center">
        <h1 className="font-heading text-xl font-semibold">Choose an organization</h1>
        <p className="text-sm text-muted-foreground">
          Research runs and reports are stored per organization. Select or create one to continue.
        </p>
        <OrganizationList
          hidePersonal
          afterSelectOrganizationUrl="/"
          afterCreateOrganizationUrl="/"
        />
      </div>
    );
  }
  return <>{children}</>;
}

/** Blocks the dashboard until a Clerk organization is active (multi-tenancy requirement). */
export function OrgGate({ children }: { children: React.ReactNode }) {
  return MOCK_MODE ? <>{children}</> : <ClerkOrgGate>{children}</ClerkOrgGate>;
}
