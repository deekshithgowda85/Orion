import "server-only";
import { NextResponse } from "next/server";
import { MOCK_MODE } from "@/lib/mock-mode";

/** Mock handlers answer only in demo mode; otherwise they pretend not to exist. */
export function mockGuard(): NextResponse | null {
  return MOCK_MODE ? null : NextResponse.json({ error: "Not found" }, { status: 404 });
}
