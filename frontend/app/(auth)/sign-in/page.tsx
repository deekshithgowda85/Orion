import type { Metadata } from "next";
import { Suspense } from "react";
import { SignIn } from "@clerk/nextjs";
import { DemoAuthForm } from "@/components/auth/DemoAuthForm";
import { clerkAppearance } from "@/components/auth/clerkAppearance";
import { MOCK_MODE } from "@/lib/mock-mode";

export const metadata: Metadata = { title: "Sign in" };

export default function SignInPage() {
  // Demo mode (no Clerk): local demo login. Otherwise Clerk's component, styled to match.
  if (MOCK_MODE) {
    return (
      <Suspense fallback={null}>
        <DemoAuthForm mode="sign-in" />
      </Suspense>
    );
  }
  // routing="hash" lets this live in a non-catch-all route (app/(auth)/sign-in/page.tsx).
  return (
    <div className="auth-form-wrap">
      <h1 className="auth-title auth-rise">Sign In</h1>
      <SignIn routing="hash" signUpUrl="/sign-up" appearance={clerkAppearance} />
    </div>
  );
}
