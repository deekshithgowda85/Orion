"use client";

import { useEffect, useState, type CSSProperties } from "react";
import { Check, TriangleAlert } from "lucide-react";

const CONFIDENCE = 0.76;
const BARS: { h: number; d: string }[] = [
  { h: 46, d: "0s" },
  { h: 62, d: "0.25s" },
  { h: 54, d: "0.5s" },
  { h: 78, d: "0.75s" },
  { h: 66, d: "1s" },
  { h: 92, d: "1.25s" },
  { h: 72, d: "1.5s" },
];

/** Counts 0 -> CONFIDENCE once on load (jumps straight to the end when reduced motion is on). */
function useCountUp(target: number, ms = 1600) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setValue(target);
      return;
    }
    let frame = 0;
    const start = performance.now() + 700;
    const tick = (now: number) => {
      const t = Math.min(1, Math.max(0, (now - start) / ms));
      setValue(target * (1 - Math.pow(1 - t, 3)));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, ms]);
  return value;
}

const delay = (d: string): CSSProperties => ({ ["--d" as string]: d });

/** Left panel of the auth screens. Pure decoration (aria-hidden), no external images. */
export function AuthHero() {
  const confidence = useCountUp(CONFIDENCE);

  return (
    <aside className="auth-hero" aria-hidden="true">
      <p className="auth-tagline auth-rise">
        Autonomous market research: from a question to a verified, citation-backed report.
      </p>

      <h2 className="auth-headline">
        <span className="auth-rise" style={delay("0.1s")}>Evidence-driven</span>
        <span className="auth-rise auth-grad-text" style={delay("0.25s")}>market intelligence.</span>
      </h2>

      <div className="auth-stage">
        <div className="auth-ring auth-ring-a">
          <i className="auth-orbit-dot" />
        </div>
        <div className="auth-ring auth-ring-b" />

        <div className="auth-device">
          <div className="auth-device-top">
            <span className="auth-ticker">AAPL &middot; Deep Audit</span>
            <span className="auth-live">Live</span>
          </div>

          <p className="auth-conf-label">OVERALL CONFIDENCE</p>
          <div className="auth-conf-row">
            <span className="auth-conf-num">{confidence.toFixed(2)}</span>
            <span className="auth-conf-pct">{Math.round(confidence * 100)}%</span>
          </div>
          <div className="auth-meter">
            <i />
          </div>

          <div className="auth-bars">
            {BARS.map((b, i) => (
              <span key={i} className="auth-bar" style={{ ["--h" as string]: `${b.h}%`, ["--d" as string]: b.d }} />
            ))}
          </div>

          <ul className="auth-steps">
            <li className="auth-step auth-step-done" style={delay("0.9s")}>
              <span className="auth-step-dot"><Check size={9} /></span>Planner
            </li>
            <li className="auth-step auth-step-done" style={delay("1.1s")}>
              <span className="auth-step-dot"><Check size={9} /></span>Market data &amp; filings
            </li>
            <li className="auth-step auth-step-run" style={delay("1.3s")}>
              <span className="auth-step-dot" />Verifier cross-checking
            </li>
            <li className="auth-step auth-step-wait" style={delay("1.5s")}>
              <span className="auth-step-dot" />Synthesizer
            </li>
          </ul>
        </div>

        <span className="auth-chip auth-chip-warn auth-chip-a">
          <TriangleAlert size={14} /> <b>Conflict flagged</b> revenue growth
        </span>
        <span className="auth-chip auth-chip-ok auth-chip-b">
          <Check size={14} /> <b>6 citations</b> verified
        </span>
      </div>
    </aside>
  );
}
