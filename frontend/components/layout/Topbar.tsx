"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserMenu } from "@/components/auth/UserMenu";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

function titleFor(pathname: string): string {
  if (pathname === "/") return "Overview";
  if (pathname === "/research/new") return "New Research";
  if (pathname.startsWith("/research/")) return "Live Run";
  if (pathname.startsWith("/reports")) return "Reports";
  if (pathname.startsWith("/workflows")) return "Workflows";
  if (pathname.startsWith("/settings")) return "Settings";
  return "Dashboard";
}

export function Topbar() {
  const pathname = usePathname();
  const onNewPage = pathname === "/research/new";

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-background/80 px-4 backdrop-blur sm:px-6">
      <div className="flex items-center gap-3">
        <span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
          MRA /
        </span>
        <span className="font-heading text-sm font-semibold">{titleFor(pathname)}</span>
      </div>
      <div className="flex items-center gap-3">
        {!onNewPage && (
          <Button asChild size="sm">
            <Link href="/research/new">
              <Plus />
              New Research
            </Link>
          </Button>
        )}
        <UserMenu />
      </div>
    </header>
  );
}
