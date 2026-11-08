import { NextResponse, type NextRequest } from "next/server";
import { registry, statusFor } from "@/lib/mock/data";
import { mockGuard } from "@/lib/mock/guard";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ run_id: string }> }) {
  const blocked = mockGuard();
  if (blocked) return blocked;
  const { run_id } = await ctx.params;
  const run = registry().get(run_id);
  if (!run) return NextResponse.json({ detail: "Run not found" }, { status: 404 });
  return NextResponse.json(statusFor(run));
}
