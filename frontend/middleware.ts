import { NextResponse, type NextRequest } from "next/server";
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { MOCK_MODE } from "@/lib/mock-mode";
import { DEMO_COOKIE } from "@/lib/mock-auth";

/** Only the Clerk sign-in / sign-up pages are public. Everything else — pages AND /api/* — requires a session. */
const isPublicRoute = createRouteMatcher(["/sign-in(.*)", "/sign-up(.*)"]);

const clerk = clerkMiddleware(async (auth, req) => {
  if (isPublicRoute(req)) return;

  if (req.nextUrl.pathname.startsWith("/api/")) {
    // Return a real 401 for the data API instead of a redirect/404, so the UI can show "signed out".
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthenticated" }, { status: 401 });
    return;
  }

  await auth.protect();
});

/** Demo mode (no Clerk): pages need the demo-login cookie; the mock /api/* data stays open. */
function mockGate(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  if (pathname.startsWith("/api/")) return NextResponse.next();

  const signedIn = Boolean(req.cookies.get(DEMO_COOKIE)?.value);
  const isAuthPage = pathname.startsWith("/sign-in") || pathname.startsWith("/sign-up");

  if (isAuthPage) return signedIn ? NextResponse.redirect(new URL("/", req.url)) : NextResponse.next();
  if (signedIn) return NextResponse.next();

  const url = new URL("/sign-in", req.url);
  if (pathname !== "/") url.searchParams.set("redirect_url", pathname + search);
  return NextResponse.redirect(url);
}

export default MOCK_MODE ? mockGate : clerk;

export const config = {
  matcher: [
    // Skip Next.js internals and static files
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
