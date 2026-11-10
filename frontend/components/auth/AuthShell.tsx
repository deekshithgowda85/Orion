"use client";

import type { ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { User } from "lucide-react";
import { MOCK_MODE } from "@/lib/mock-mode";
import { AuthHero } from "./AuthHero";

/** Split-screen frame shared by /sign-in and /sign-up: animated hero on the left, form panel on the right. */
export function AuthShell({ children }: { children: ReactNode }) {
  const onSignUp = usePathname()?.startsWith("/sign-up") ?? false;

  return (
    <div className="auth-root">
      <div className="auth-frame">
        <AuthHero />
        <section className="auth-panel">
          <header className="auth-panel-head">
            <Link href="/sign-in" className="auth-brand">
              <Image src="/orion_logo.svg" alt="" width={36} height={36} priority />
              <span>Orion</span>
            </Link>
            <Link href={onSignUp ? "/sign-in" : "/sign-up"} className="auth-switch">
              <User size={18} aria-hidden />
              {onSignUp ? "Sign In" : "Sign Up"}
            </Link>
          </header>

          <main className="auth-panel-main">{children}</main>

          <footer className="auth-panel-foot">
            <span>&copy; {new Date().getFullYear()} Orion</span>
            {MOCK_MODE && <span className="auth-demo-pill">Demo mode</span>}
          </footer>
        </section>
      </div>
    </div>
  );
}
