"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FilePlus2,
  FileText,
  GitBranch,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  type LucideIcon,
} from "lucide-react";
import Image from "next/image";
import { OrgSwitcher } from "@/components/auth/OrgSwitcher";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useActiveRunCount } from "@/hooks/useActiveRunCount";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Pathname prefix that marks this item active. */
  match: string;
  exact?: boolean;
}

const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, match: "/", exact: true },
  { href: "/research/new", label: "New Research", icon: FilePlus2, match: "/research" },
  { href: "/reports", label: "Reports", icon: FileText, match: "/reports" },
  { href: "/workflows", label: "Workflows", icon: GitBranch, match: "/workflows" },
  { href: "/settings", label: "Settings", icon: Settings, match: "/settings" },
];

function ActiveRunsIndicator({ count, collapsed }: { count: number; collapsed: boolean }) {
  if (count <= 0) return null;

  if (collapsed) {
    return (
      <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 font-mono text-[10px] font-semibold text-primary-foreground">
        {count}
      </span>
    );
  }

  return (
    <span
      className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 font-mono text-[11px] text-primary"
      aria-label={`${count} active runs`}
    >
      <span className="relative flex size-1.5">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-50" />
        <span className="relative inline-flex size-1.5 rounded-full bg-primary" />
      </span>
      {count}
    </span>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const storedCollapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const activeCount = useActiveRunCount();

  // Avoid a hydration mismatch with the persisted collapsed flag.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const collapsed = mounted && storedCollapsed;

  return (
    <aside
      className={cn(
        "sticky top-0 flex h-screen shrink-0 flex-col border-r border-border bg-surface/80 backdrop-blur transition-[width] duration-200",
        collapsed ? "w-[68px]" : "w-60",
      )}
      aria-label="Primary"
    >
      {/* Brand */}
      <div
        className={cn(
          "flex h-16 items-center border-b border-border px-4",
          collapsed ? "justify-center" : "gap-3",
        )}
      >
        <div className="flex size-9 shrink-0 items-center justify-center overflow-hidden">
          <Image
            src="/orion_logo.svg"
            alt="Orion logo mark"
            width={36}
            height={36}
            priority
            className="h-full w-full object-contain"
          />
        </div>
        {!collapsed && (
          <p className="truncate font-heading text-sm font-bold">Orion</p>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 p-3">
        {NAV_ITEMS.map((item) => {
          const active = item.exact ? pathname === item.match : pathname.startsWith(item.match);
          const isReports = item.href === "/reports";
          const Icon = item.icon;

          const link = (
            <Link
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group relative flex h-10 items-center rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                collapsed ? "justify-center px-0" : "gap-3 px-3",
                active
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {active && (
                <span className="absolute left-0 top-2 h-6 w-0.5 rounded-r bg-primary" aria-hidden />
              )}
              <span className="relative">
                <Icon className="size-[18px] shrink-0" />
                {isReports && collapsed && <ActiveRunsIndicator count={activeCount} collapsed />}
              </span>
              {!collapsed && <span className="truncate">{item.label}</span>}
              {isReports && !collapsed && <ActiveRunsIndicator count={activeCount} collapsed={false} />}
            </Link>
          );

          return collapsed ? (
            <Tooltip key={item.href}>
              <TooltipTrigger asChild>{link}</TooltipTrigger>
              <TooltipContent side="right">
                {item.label}
                {isReports && activeCount > 0 ? ` · ${activeCount} active` : ""}
              </TooltipContent>
            </Tooltip>
          ) : (
            <div key={item.href}>{link}</div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="space-y-2 border-t border-border p-3">
        <div className={cn("flex", collapsed && "justify-center")}>
          <OrgSwitcher collapsed={collapsed} />
        </div>
        <button
          type="button"
          onClick={toggleSidebar}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "flex h-9 w-full items-center rounded-lg text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
            collapsed ? "justify-center" : "gap-2 px-3",
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="size-4" />
          ) : (
            <>
              <PanelLeftClose className="size-4" />
              Collapse
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
