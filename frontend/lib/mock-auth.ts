/**
 * Demo-only authentication, used when NEXT_PUBLIC_MOCK_MODE=true (Clerk is off).
 *
 * Accounts live in this browser's localStorage and the "session" is a plain cookie that
 * only tells the middleware "a demo user signed in". This is NOT real security: it exists
 * so the dashboard can show a login / registration flow without Clerk keys or a backend.
 * Never type a real password into it. Real deployments use Clerk (mock mode off).
 */

export const DEMO_COOKIE = "orion_demo_session";
const USERS_KEY = "orion_demo_users";
const USER_KEY = "orion_demo_user";
const SESSION_SECONDS = 60 * 60 * 24;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Built-in account so a demo can start with one click. */
export const DEMO_ACCOUNT = {
  name: "Demo User",
  email: "demo@orion.dev",
  password: "orion123",
} as const;

export interface DemoUser {
  name: string;
  email: string;
}

export type DemoAuthResult = { ok: true; user: DemoUser } | { ok: false; error: string };

type StoredUsers = Record<string, { name: string; hash: string }>;

const fail = (error: string): DemoAuthResult => ({ ok: false, error });
const normalizeEmail = (email: string) => email.trim().toLowerCase();

async function hashPassword(password: string): Promise<string> {
  const subtle = typeof crypto !== "undefined" ? crypto.subtle : undefined;
  if (subtle) {
    const digest = await subtle.digest("SHA-256", new TextEncoder().encode(`orion-demo:${password}`));
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  }
  // crypto.subtle only exists on https / localhost; fall back so the demo still works elsewhere.
  return `plain:${btoa(encodeURIComponent(password))}`;
}

function readUsers(): StoredUsers {
  try {
    const raw = localStorage.getItem(USERS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? (parsed as StoredUsers) : {};
  } catch {
    return {}; // storage unavailable or corrupted: behave as "no accounts yet"
  }
}

function writeUsers(users: StoredUsers): void {
  try {
    localStorage.setItem(USERS_KEY, JSON.stringify(users));
  } catch {
    /* storage unavailable: the account just will not persist */
  }
}

export function startDemoSession(user: DemoUser): void {
  try {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    /* storage unavailable: the cookie below still lets the user in */
  }
  document.cookie = `${DEMO_COOKIE}=1; path=/; max-age=${SESSION_SECONDS}; SameSite=Lax`;
}

export function endDemoSession(): void {
  try {
    localStorage.removeItem(USER_KEY);
  } catch {
    /* nothing to clear */
  }
  document.cookie = `${DEMO_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
}

export function getDemoUser(): DemoUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    const parsed = raw ? (JSON.parse(raw) as Partial<DemoUser>) : null;
    return parsed && typeof parsed.name === "string" && typeof parsed.email === "string"
      ? { name: parsed.name, email: parsed.email }
      : null;
  } catch {
    return null;
  }
}

export async function registerDemoUser(input: {
  name: string;
  email: string;
  password: string;
}): Promise<DemoAuthResult> {
  const name = input.name.trim();
  const email = normalizeEmail(input.email);
  if (!name) return fail("Enter your name.");
  if (!EMAIL_RE.test(email)) return fail("Enter a valid email address.");
  if (input.password.length < 6) return fail("Password must be at least 6 characters.");

  const users = readUsers();
  if (email === DEMO_ACCOUNT.email || users[email]) {
    return fail("An account with this email already exists. Sign in instead.");
  }
  users[email] = { name, hash: await hashPassword(input.password) };
  writeUsers(users);

  const user = { name, email };
  startDemoSession(user);
  return { ok: true, user };
}

export async function signInDemoUser(emailInput: string, password: string): Promise<DemoAuthResult> {
  const email = normalizeEmail(emailInput);
  if (!EMAIL_RE.test(email) || !password) return fail("Enter your email and password.");

  let user: DemoUser | null = null;
  if (email === DEMO_ACCOUNT.email) {
    if (password === DEMO_ACCOUNT.password) user = { name: DEMO_ACCOUNT.name, email };
  } else {
    const stored = readUsers()[email];
    if (stored && stored.hash === (await hashPassword(password))) user = { name: stored.name, email };
  }
  if (!user) return fail("Incorrect email or password.");

  startDemoSession(user);
  return { ok: true, user };
}

export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : (parts[0] ?? "DM").slice(0, 2);
  return letters.toUpperCase();
}
