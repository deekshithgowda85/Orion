import { NextResponse, type NextRequest } from "next/server";
import { createRun } from "@/lib/mock/data";
import { mockGuard } from "@/lib/mock/guard";

export async function POST(req: NextRequest) {
  const blocked = mockGuard();
  if (blocked) return blocked;

  const body: unknown = await req.json().catch(() => null);
  if (typeof body !== "object" || body === null) {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }
  const b = body as Record<string, unknown>;
  const ticker = typeof b.ticker === "string" ? b.ticker.trim() : "";
  const query = typeof b.query === "string" ? b.query.trim() : "";
  if (!ticker || !query) {
    return NextResponse.json({ detail: "ticker and query are required" }, { status: 422 });
  }
  const run = createRun({
    ticker,
    quarter: typeof b.quarter === "string" ? b.quarter : undefined,
    query,
    workflow_type: typeof b.workflow_type === "string" ? b.workflow_type : "deep_audit",
    priority: typeof b.priority === "string" ? b.priority : "standard",
  });
  return NextResponse.json({ run_id: run.run_id, status: "queued" }, { status: 202 });
}
