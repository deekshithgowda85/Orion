import type { Metadata } from "next";
import { Suspense } from "react";
import { SignUp } from "@clerk/nextjs";
import { DemoAuthForm } from "@/components/auth/DemoAuthForm";
import { clerkAppearance } from "@/components/auth/clerkAppearance";
import { MOCK_MODE } from "@/lib/mock-mode";

export const metadata: Metadata = { title: "Create account" };

export default function SignUpPage() {
  if (MOCK_MODE) {
    return (
      <Suspense fallback={null}>
        <DemoAuthForm mode="sign-up" />
      </Suspense>
    );
  }
  return (
    <div className="auth-form-wrap">
      <h1 className="auth-title auth-rise">Create account</h1>
      <SignUp routing="hash" signInUrl="/sign-in" appearance={clerkAppearance} />
    </div>
  );
}
