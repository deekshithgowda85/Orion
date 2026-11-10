"use client";

import { useState, type CSSProperties, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Eye, EyeOff, Loader2, LogIn, UserPlus } from "lucide-react";
import { DEMO_ACCOUNT, registerDemoUser, signInDemoUser } from "@/lib/mock-auth";

/** Only allow same-site paths as a post-login target. */
function safeRedirect(target: string | null): string {
  return target && target.startsWith("/") && !target.startsWith("//") ? target : "/";
}

const delay = (d: string): CSSProperties => ({ ["--d" as string]: d });

/** Demo-mode sign-in / registration form (Clerk is off). Styled by app/(auth)/auth.css. */
export function DemoAuthForm({ mode }: { mode: "sign-in" | "sign-up" }) {
  const redirectTo = safeRedirect(useSearchParams().get("redirect_url"));
  const isSignUp = mode === "sign-up";

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shake, setShake] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = isSignUp
        ? await registerDemoUser({ name, email, password })
        : await signInDemoUser(email, password);
      if (!result.ok) {
        setError(result.error);
        setShake(true);
        return;
      }
      // Full navigation so the middleware sees the new session cookie.
      window.location.assign(redirectTo);
    } finally {
      setBusy(false);
    }
  }

  function fillDemoAccount() {
    setEmail(DEMO_ACCOUNT.email);
    setPassword(DEMO_ACCOUNT.password);
    setError(null);
  }

  const invalid = error ? true : undefined;

  return (
    <div className="auth-form-wrap">
      <h1 className="auth-title auth-rise">{isSignUp ? "Create account" : "Sign In"}</h1>

      <form
        onSubmit={onSubmit}
        onAnimationEnd={() => setShake(false)}
        className={`auth-form${shake ? " auth-shake" : ""}`}
        noValidate
      >
        {isSignUp && (
          <div className="auth-field auth-rise" style={delay("0.08s")}>
            <input
              className="auth-input"
              aria-label="Full name"
              placeholder="Full name"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
        )}

        <div className="auth-field auth-rise" style={delay("0.12s")}>
          <input
            className="auth-input"
            type="email"
            aria-label="Email"
            aria-invalid={invalid}
            placeholder="Email address"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="auth-field auth-rise" style={delay("0.18s")}>
          <input
            className="auth-input auth-input-pw"
            type={showPassword ? "text" : "password"}
            aria-label="Password"
            aria-invalid={invalid}
            placeholder={isSignUp ? "Password (at least 6 characters)" : "Password"}
            autoComplete={isSignUp ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button
            type="button"
            className="auth-eye"
            aria-label={showPassword ? "Hide password" : "Show password"}
            aria-pressed={showPassword}
            onClick={() => setShowPassword((v) => !v)}
          >
            {showPassword ? <Eye size={20} /> : <EyeOff size={20} />}
          </button>
        </div>

        {error && (
          <p role="alert" className="auth-error">
            {error}
          </p>
        )}

        {!isSignUp && (
          <button type="button" className="auth-link auth-rise" style={delay("0.22s")} onClick={fillDemoAccount}>
            Use demo account
          </button>
        )}

        <button type="submit" className="auth-submit auth-rise" style={delay("0.28s")} disabled={busy}>
          {busy ? <Loader2 size={20} className="animate-spin" /> : isSignUp ? <UserPlus size={20} /> : <LogIn size={20} />}
          {isSignUp ? "Create account" : "Sign In"}
        </button>
      </form>

      <p className="auth-switch-text auth-rise" style={delay("0.34s")}>
        {isSignUp ? "Already have an account? " : "New to Orion? "}
        <Link href={isSignUp ? "/sign-in" : "/sign-up"} className="auth-link" style={{ marginLeft: 0 }}>
          {isSignUp ? "Sign in" : "Create an account"}
        </Link>
      </p>

      <p className="auth-note auth-rise" style={delay("0.4s")}>
        Demo mode: accounts are stored only in this browser and are not secure. Try{" "}
        <code>{DEMO_ACCOUNT.email}</code> / <code>{DEMO_ACCOUNT.password}</code>, or register. Never use a real
        password.
      </p>
    </div>
  );
}
