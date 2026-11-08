import { NextResponse, type NextRequest } from "next/server";
import { confidenceFor, registry, reportFor, statusFor } from "@/lib/mock/data";
import { mockGuard } from "@/lib/mock/guard";

export async function GET(req: NextRequest) {
  const blocked = mockGuard();
  if (blocked) return blocked;

  const q = req.nextUrl.searchParams;
  const page = Math.max(1, Number(q.get("page") ?? 1) || 1);
  const pageSize = Math.min(100, Math.max(1, Number(q.get("page_size") ?? 20) || 20));
  const ticker = (q.get("ticker") ?? "").toUpperCase();
  const workflow = q.get("workflow_type") ?? "";
  const status = q.get("status") ?? "";
  const minConf = Number(q.get("min_confidence") ?? 0) || 0;
  const from = q.get("date_from") ? Date.parse(q.get("date_from") as string) : null;
  const to = q.get("date_to") ? Date.parse(`${q.get("date_to")}T23:59:59`) : null;

  const rows = [...registry().values()]
    .sort((a, b) => b.started - a.started)
    .map((run) => ({ run, s: statusFor(run) }))
    .filter(({ run, s }) => {
      if (ticker && !run.ticker.includes(ticker)) return false;
      if (workflow && run.workflow_type !== workflow) return false;
      if (status && s.status !== status) return false;
      if (minConf > 0 && !(s.status === "completed" && confidenceFor(run) >= minConf)) return false;
      if (from !== null && run.started < from) return false;
      if (to !== null && run.started > to) return false;
      return true;
    });

  const items = rows.slice((page - 1) * pageSize, page * pageSize).map(({ run, s }) => ({
    ...s,
    executive_summary: s.status === "completed" && run.scenario !== "long" ? reportFor(run).executive_summary : null,
  }));

  return NextResponse.json({ items, total: rows.length, page, page_size: pageSize });
}
