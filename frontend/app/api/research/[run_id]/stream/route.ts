import type { NextRequest } from "next/server";
import { eventsFor, registry, totalSeconds } from "@/lib/mock/data";
import { mockGuard } from "@/lib/mock/guard";

export const dynamic = "force-dynamic";

/** SSE: replays events already due, then emits the rest in real time; closes after the terminal event. */
export async function GET(req: NextRequest, ctx: { params: Promise<{ run_id: string }> }) {
  const blocked = mockGuard();
  if (blocked) return blocked;
  const { run_id } = await ctx.params;
  const run = registry().get(run_id);
  if (!run) return new Response(JSON.stringify({ detail: "Run not found" }), { status: 404 });

  const events = eventsFor(run);
  const enc = new TextEncoder();
  const timers: ReturnType<typeof setTimeout>[] = [];
  let heartbeat: ReturnType<typeof setInterval> | undefined;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let closed = false;
      const close = () => {
        if (closed) return;
        closed = true;
        timers.forEach(clearTimeout);
        if (heartbeat) clearInterval(heartbeat);
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      };
      const send = (id: number, type: string, payload: Record<string, unknown>) => {
        if (closed) return;
        controller.enqueue(enc.encode(`id: ${id}\ndata: ${JSON.stringify({ type, payload })}\n\n`));
        if (type === "report_ready" || type === "run_failed") setTimeout(close, 50);
      };

      controller.enqueue(enc.encode("retry: 3000\n\n"));
      const elapsed = (Date.now() - run.started) / 1000;
      events.forEach((e, i) => {
        const delay = Math.max(0, (e.at - elapsed) * 1000);
        if (delay === 0) send(i + 1, e.type, e.payload);
        else timers.push(setTimeout(() => send(i + 1, e.type, e.payload), delay));
      });
      if (elapsed >= totalSeconds(run)) setTimeout(close, 100);

      heartbeat = setInterval(() => {
        if (!closed) controller.enqueue(enc.encode(": ping\n\n"));
      }, 10_000);
      req.signal.addEventListener("abort", close);
    },
    cancel() {
      timers.forEach(clearTimeout);
      if (heartbeat) clearInterval(heartbeat);
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
