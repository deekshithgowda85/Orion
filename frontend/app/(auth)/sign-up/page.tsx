import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { SignUp } from "@clerk/nextjs";
import { MOCK_MODE } from "@/lib/mock-mode";

export const metadata: Metadata = { title: "Create account" };

export default function SignUpPage() {
  if (MOCK_MODE) redirect("/");
  return <SignUp routing="hash" signInUrl="/sign-in" />;
}
