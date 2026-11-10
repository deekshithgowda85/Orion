"use client";

import { useEffect, useRef, useState } from "react";
import { UserButton } from "@clerk/nextjs";
import { LogOut } from "lucide-react";
import { MOCK_MODE } from "@/lib/mock-mode";
import { endDemoSession, getDemoUser, initialsOf, type DemoUser } from "@/lib/mock-auth";

/** Demo-mode avatar with a sign-out menu (Clerk is off). */
function DemoUserMenu() {
  const [user, setUser] = useState<DemoUser | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Read after mount so server and client markup match.
  useEffect(() => {
    setUser(getDemoUser());
  }, []);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function signOut() {
    endDemoSession();
    window.location.assign("/sign-in");
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={user?.email ?? "Demo mode — Clerk is disabled"}
        className="flex size-8 items-center justify-center rounded-full bg-primary/20 font-mono text-[11px] text-primary ring-1 ring-border"
      >
        {user ? initialsOf(user.name) : "DM"}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-10 z-40 w-56 rounded-lg border border-border bg-card p-1 shadow-lg"
        >
          <div className="px-3 py-2">
            <p className="truncate text-sm font-medium">{user?.name ?? "Demo user"}</p>
            <p className="truncate text-xs text-muted-foreground">{user?.email ?? "Demo mode"}</p>
          </div>
          <div className="my-1 h-px bg-border" />
          <button
            type="button"
            role="menuitem"
            onClick={signOut}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-muted"
          >
            <LogOut className="size-4" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export function UserMenu() {
  if (MOCK_MODE) return <DemoUserMenu />;
  return <UserButton appearance={{ elements: { avatarBox: "size-8 ring-1 ring-border" } }} />;
}
