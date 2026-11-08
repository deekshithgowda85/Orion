import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { SignIn } from "@clerk/nextjs";
import { MOCK_MODE } from "@/lib/mock-mode";

export const metadata: Metadata = { title: "Sign in" };

export default function SignInPage() {
  if (MOCK_MODE) redirect("/");
  // routing="hash" lets this live in a non-catch-all route (app/(auth)/sign-in/page.tsx).
  return <SignIn routing="hash" signUpUrl="/sign-up" />;
}
