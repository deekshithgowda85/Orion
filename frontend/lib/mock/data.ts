import "server-only";

/**
 * In-memory fake of the Layer 4 BFF, used only when NEXT_PUBLIC_MOCK_MODE=true (dev).
 * Special tickers exercise the awkward cases:
 *   THIN → free-tier gaps: no market snapshot / options, null P/E + FCF yield, `errors` list
 *   FAIL → run fails part-way through
 *   LONG → huge report (60 sections, 400 citations, 600 trace entries)
 *   anything else → healthy run (~22 s)
 */

export type Scenario = "ok" | "thin" | "fail" | "long";

export interface MockRun {
  run_id: string;
  ticker: string;
  quarter: string | null;
  query: string;
  workflow_type: string;
  priority: string;
  started: number;
  scenario: Scenario;
}

export interface MockEvent {
  at: number; // seconds after start
  type: string;
  payload: Record<string, unknown>;
}

const OK_TOTAL = 22;
const FAIL_AT = 12;

const globalRef = globalThis as typeof globalThis & { __mraMockRuns?: Map<string, MockRun> };

export function scenarioFor(ticker: string): Scenario {
  const t = ticker.toUpperCase();
  if (t === "THIN") return "thin";
  if (t === "FAIL") return "fail";
  if (t === "LONG") return "long";
  return "ok";
}

function hash(s: string): number {
  let h = 7;
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

export function confidenceFor(run: MockRun): number {
  if (run.scenario === "thin") return 0.58;
  return Number((0.62 + (hash(run.ticker) % 31) / 100).toFixed(2));
}

function seed(map: Map<string, MockRun>): void {
  const now = Date.now();
  const rows: Array<[string, Scenario, number, string, string]> = [
    ["AAPL", "ok", 0.4, "deep_audit", "Assess services margin sustainability vs consensus"],
    ["MSFT", "ok", 1.5, "earnings_pulse", "Summarise cloud growth drivers from the latest earnings call"],
    ["NVDA", "ok", 3, "daily_scan", "Daily scan: news, filings and options flow"],
    ["TSLA", "thin", 5, "deep_audit", "Free-cash-flow quality and capex outlook"],
    ["AMD", "fail", 7, "deep_audit", "Compare data-center share trajectory against peers"],
    ["META", "ok", 26, "earnings_pulse", "Ad pricing vs impressions trend, any guidance change?"],
  ];
  rows.forEach(([ticker, scenario, hoursAgo, workflow_type, query], i) => {
    const run_id = `run_demo_${String(i + 1).padStart(3, "0")}`;
    map.set(run_id, {
      run_id,
      ticker,
      quarter: workflow_type === "earnings_pulse" ? "2025Q3" : null,
      query,
      workflow_type,
      priority: "standard",
      started: now - hoursAgo * 3600_000,
      scenario,
    });
  });
}

export function registry(): Map<string, MockRun> {
  if (!globalRef.__mraMockRuns) {
    globalRef.__mraMockRuns = new Map();
    seed(globalRef.__mraMockRuns);
  }
  return globalRef.__mraMockRuns;
}

export function createRun(input: {
  ticker: string;
  quarter?: string;
  query: string;
  workflow_type: string;
  priority: string;
}): MockRun {
  const run: MockRun = {
    run_id: `run_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`,
    ticker: input.ticker.toUpperCase(),
    quarter: input.quarter ?? null,
    query: input.query,
    workflow_type: input.workflow_type,
    priority: input.priority,
    started: Date.now(),
    scenario: scenarioFor(input.ticker),
  };
  registry().set(run.run_id, run);
  return run;
}

/* ------------------------------ events ------------------------------ */

function stepPair(
  agent: string,
  label: string,
  from: number,
  to: number,
  pct: number,
  summary: string,
): MockEvent[] {
  return [
    { at: from, type: "step_started", payload: { step_id: agent, agent, label } },
    {
      at: to,
      type: "step_completed",
      payload: {
        step_id: agent,
        agent,
        label,
        duration_ms: Math.round((to - from) * 1000),
        summary,
        progress_pct: pct,
      },
    },
  ];
}

export function eventsFor(run: MockRun): MockEvent[] {
  const ev: MockEvent[] = [
    { at: 0, type: "run_started", payload: { message: `Run started for ${run.ticker}` } },
    ...stepPair("planner", "Planning research", 0.5, 2.5, 12, "4 sub-tasks planned"),
    ...stepPair("market_data", "Fetching market data", 3, 8, 30, "Price, volume, fundamentals"),
    ...stepPair("filings", "Reading SEC filings", 3, 10, 45, "10-Q, 10-K parsed"),
    ...stepPair("news", "Scanning news & sentiment", 3.5, 9, 58, "23 articles scored"),
    ...stepPair("quant", "Running quant checks", 10, 14, 72, "Ratios and z-scores computed"),
    {
      at: 15,
      type: "conflict_found",
      payload: {
        metric: "Revenue growth YoY",
        value_a: "12.4%",
        source_a: "Company 10-Q (sec.gov)",
        value_b: "11.1%",
        source_b: "Yahoo Finance",
        severity: "medium",
        resolution: "Preferring the filed figure",
      },
    },
    ...stepPair("verifier", "Cross-verifying sources", 14.5, 17, 84, "1 conflict flagged"),
    ...stepPair("synthesizer", "Synthesizing report", 17.5, 21, 95, "Report drafted"),
  ];
  if (run.scenario === "thin") {
    ev.push({
      at: 8.5,
      type: "conflict_found",
      payload: {
        metric: "Free cash flow",
        value_a: "n/a",
        source_a: "yfinance (rate limited)",
        value_b: "1.2B",
        source_b: "Company 10-Q (sec.gov)",
        severity: "low",
        resolution: null,
      },
    });
  }
  if (run.scenario === "fail") {
    const cut = ev.filter((e) => e.at < FAIL_AT);
    cut.push({
      at: FAIL_AT,
      type: "run_failed",
      payload: { error: "Filings agent: SEC EDGAR request timed out after 3 retries" },
    });
    return cut.sort((a, b) => a.at - b.at);
  }
  ev.push({
    at: OK_TOTAL,
    type: "report_ready",
    payload: { report_id: run.run_id, confidence_score: confidenceFor(run) },
  });
  return ev.sort((a, b) => a.at - b.at);
}

export function totalSeconds(run: MockRun): number {
  return run.scenario === "fail" ? FAIL_AT : OK_TOTAL;
}

/* ------------------------------ status ------------------------------ */

export function statusFor(run: MockRun): Record<string, unknown> {
  const elapsed = (Date.now() - run.started) / 1000;
  const total = totalSeconds(run);
  const done = elapsed >= total;
  const seen = eventsFor(run).filter((e) => e.at <= elapsed);

  let progress = 0;
  let step: string | null = null;
  let conflicts = 0;
  for (const e of seen) {
    if (typeof e.payload.progress_pct === "number") progress = e.payload.progress_pct;
    if (e.type === "step_started") step = String(e.payload.label);
    if (e.type === "conflict_found") conflicts += 1;
  }

  const status = done ? (run.scenario === "fail" ? "failed" : "completed") : elapsed < 0.4 ? "queued" : "running";
  const errors = run.scenario === "thin" ? THIN_ERRORS : [];

  return {
    run_id: run.run_id,
    ticker: run.ticker,
    query: run.query,
    workflow_type: run.workflow_type,
    status,
    progress_pct: status === "completed" ? 100 : progress,
    current_step: done ? null : step,
    conflict_count: conflicts,
    confidence_score: status === "completed" ? confidenceFor(run) : null,
    started_at: new Date(run.started).toISOString(),
    completed_at: done ? new Date(run.started + total * 1000).toISOString() : null,
    duration_seconds: done ? total : null,
    error: status === "failed" ? "Filings agent: SEC EDGAR request timed out after 3 retries" : null,
    errors: done || run.scenario === "thin" ? errors : [],
  };
}

const THIN_ERRORS = [
  "market_data: yfinance rate limited (HTTP 429)",
  "options: no options chain available on free tier",
];

/* ------------------------------ report ------------------------------ */

const LOREM =
  "Margins expanded on mix shift toward higher-value services while operating expenses grew slower than revenue [1]. " +
  "Management reiterated full-year guidance, though the consensus estimate sits slightly above the midpoint [2]. " +
  "Free cash flow conversion remained healthy relative to the trailing four quarters [3].";

export function reportFor(run: MockRun): Record<string, unknown> {
  const conf = confidenceFor(run);
  const thin = run.scenario === "thin";
  const long = run.scenario === "long";

  const nCitations = long ? 400 : thin ? 3 : 6;
  const types = ["filing", "market_data", "news", "analyst", "transcript"];
  const citations = Array.from({ length: nCitations }, (_, i) => ({
    id: i + 1,
    source_url: `https://example.com/${types[i % types.length]}/${run.ticker.toLowerCase()}/${i + 1}`,
    source_type: types[i % types.length],
    metric: ["Revenue", "EPS", "Gross margin", "FCF", "Guidance"][i % 5],
    value: thin && i === 2 ? null : `${(10 + (i % 17) * 1.3).toFixed(1)}%`,
    confidence: thin && i === 1 ? null : Number((0.55 + ((i * 7) % 40) / 100).toFixed(2)),
  }));

  const nSections = long ? 60 : 4;
  const sections = Array.from({ length: nSections }, (_, i) => ({
    id: `sec_${i + 1}`,
    title: ["Business overview", "Financial performance", "Valuation", "Risks & conflicts"][i % 4] + (long ? ` (${i + 1})` : ""),
    content: long ? `${LOREM}\n\n`.repeat(40) : `${LOREM}\n\n${LOREM}`,
  }));

  const nTrace = long ? 600 : 12;
  const trace_log = Array.from({ length: nTrace }, (_, i) => ({
    id: `tr_${i + 1}`,
    timestamp: new Date(run.started + i * 1500).toISOString(),
    agent: ["planner", "market_data", "filings", "news", "quant", "verifier"][i % 6],
    tool: ["get_quote", "search_filings", "fetch_news", "compute_ratios", "cross_check"][i % 5],
    input: { ticker: run.ticker, attempt: 1, nested: { window: "90d", fields: ["close", "volume"] } },
    output_summary: `Returned ${10 + i} records`,
    tokens_in: 400 + i * 13,
    tokens_out: 120 + i * 5,
    duration_ms: 300 + ((i * 137) % 2200),
    self_correction: i === 7 ? "First query used the wrong fiscal year; re-ran with FY2025." : null,
  }));

  return {
    run_id: run.run_id,
    ticker: run.ticker,
    quarter: run.quarter,
    generated_at: new Date(run.started + OK_TOTAL * 1000).toISOString(),
    confidence_score: conf,
    executive_summary: thin
      ? "Partial analysis: market snapshot and options data were unavailable on the free tier, so valuation conclusions rest on filings and news only [1][2]."
      : `${run.ticker} shows resilient fundamentals with one flagged cross-source discrepancy on revenue growth [1]. ${LOREM}`,
    errors: thin ? THIN_ERRORS : [],
    market_snapshot: thin
      ? null
      : { price: 187.42, market_cap: 2_890_000_000_000, pe_ratio: 29.1, fcf_yield: 0.034, currency: "USD" },
    options_data: thin ? null : { iv_30d: 0.27, put_call_ratio: 0.82, next_expiry: "2026-11-20" },
    key_metrics: thin
      ? [
          { label: "Price", value: null, change_pct: null, source: null },
          { label: "P/E", value: null, change_pct: null, source: null },
          { label: "FCF yield", value: null, change_pct: null, source: null },
          { label: "Revenue growth", value: "12.4%", change_pct: 1.3, source: "sec.gov" },
        ]
      : [
          { label: "Price", value: "$187.42", change_pct: 1.24, source: "yfinance" },
          { label: "P/E", value: "29.1", change_pct: -0.8, source: "yfinance" },
          { label: "FCF yield", value: "3.4%", change_pct: 0.2, source: "sec.gov" },
          { label: "Revenue growth", value: "12.4%", change_pct: 1.3, source: "sec.gov" },
        ],
    sections,
    citations,
    raw_data: { ticker: run.ticker, fundamentals: { revenue: 94_800_000_000, eps: 1.46 }, sources: citations.length },
    trace_log,
  };
}

/* ------------------------------- PDF -------------------------------- */

/** Tiny valid one-page PDF so the Download button can be exercised without a backend. */
export function mockPdf(title: string): Uint8Array {
  const text = title.replace(/[()\\]/g, "");
  const stream = `BT /F1 18 Tf 72 720 Td (${text}) Tj ET`;
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objs.forEach((o, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  offsets.forEach((o) => {
    out += `${String(o).padStart(10, "0")} 00000 n \n`;
  });
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return new TextEncoder().encode(out);
}
