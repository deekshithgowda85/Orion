import { NextResponse } from "next/server";
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { MOCK_MODE } from "@/lib/mock-mode";

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

export default MOCK_MODE ? () => NextResponse.next() : clerk;

export const config = {
  matcher: [
    // Skip Next.js internals and static files
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
