import { NextResponse, type NextRequest } from "next/server";
import { mockPdf, registry, reportFor, statusFor } from "@/lib/mock/data";
import { mockGuard } from "@/lib/mock/guard";

export async function GET(req: NextRequest, ctx: { params: Promise<{ run_id: string }> }) {
  const blocked = mockGuard();
  if (blocked) return blocked;
  const { run_id } = await ctx.params;
  const run = registry().get(run_id);
  if (!run) return NextResponse.json({ detail: "Run not found" }, { status: 404 });
  if (statusFor(run).status !== "completed") {
    return NextResponse.json({ detail: "Report not ready" }, { status: 409 });
  }
  if (req.nextUrl.searchParams.get("format") === "pdf") {
    const bytes = mockPdf(`Mock report - ${run.ticker}`);
    return new NextResponse(bytes.buffer as ArrayBuffer, {
      headers: { "Content-Type": "application/pdf" },
    });
  }
  return NextResponse.json(reportFor(run));
}
