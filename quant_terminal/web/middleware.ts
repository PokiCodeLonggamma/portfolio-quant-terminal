import { NextResponse, type NextRequest } from "next/server";

/** Redirect to /login if the qt_auth cookie is missing on any (dashboard) route.
 *
 * The matcher excludes /login itself, Next.js internals, and static assets so
 * we don't break the login page or kill the build.
 */
export function middleware(req: NextRequest) {
  // /login + /api are exempt — they're either public (login) or hit the backend (api)
  const pathname = req.nextUrl.pathname;
  if (pathname.startsWith("/login") || pathname.startsWith("/api")) {
    return NextResponse.next();
  }

  const cookie = req.cookies.get("qt_auth");
  if (!cookie) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    if (pathname !== "/") {
      url.searchParams.set("next", pathname);
    }
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    // Run on everything EXCEPT next-internal paths + favicons + manifest
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|manifest.json).*)",
  ],
};
