"use client";

import { OrganizationSwitcher } from "@clerk/nextjs";
import { MOCK_MODE } from "@/lib/mock-mode";
import { cn } from "@/lib/utils";

interface OrgSwitcherProps {
  collapsed?: boolean;
  triggerClassName?: string;
}

/**
 * Organization switcher. `hidePersonal` is on because every API call is
 * tenant-scoped by the Clerk org in the session token; a personal workspace
 * has no org, so the BFF would have nothing to scope by.
 */
export function OrgSwitcher({ collapsed = false, triggerClassName }: OrgSwitcherProps) {
  if (MOCK_MODE) {
    return (
      <div
        className={cn(
          "rounded-lg border border-border bg-card px-2 py-2 text-center font-mono text-[11px] text-muted-foreground",
          collapsed && "px-1",
        )}
      >
        {collapsed ? "DEMO" : "Demo organization"}
      </div>
    );
  }
  return (
    <OrganizationSwitcher
      hidePersonal
      afterCreateOrganizationUrl="/"
      afterSelectOrganizationUrl="/"
      appearance={{
        elements: {
          rootBox: collapsed ? "w-10" : "w-full",
          organizationSwitcherTrigger: cn(
            "w-full rounded-lg border border-border bg-card px-2 py-2 hover:bg-muted",
            collapsed && "justify-center px-1",
            triggerClassName,
          ),
          organizationPreviewTextContainer: collapsed ? "hidden" : "",
          organizationSwitcherTriggerIcon: collapsed ? "hidden" : "",
        },
      }}
    />
  );
}
