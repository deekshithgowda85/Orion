"use client";

import { UserButton } from "@clerk/nextjs";
import { MOCK_MODE } from "@/lib/mock-mode";

export function UserMenu() {
  if (MOCK_MODE) {
    return (
      <span
        className="flex size-8 items-center justify-center rounded-full bg-primary/20 font-mono text-[11px] text-primary ring-1 ring-border"
        title="Demo mode — Clerk is disabled"
      >
        DM
      </span>
    );
  }
  return <UserButton appearance={{ elements: { avatarBox: "size-8 ring-1 ring-border" } }} />;
}
