import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login"];
const COOKIE_NAME = "auth_token";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public paths
  if (PUBLIC_PATHS.some(p => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Allow static assets and API rewrites
  if (pathname.startsWith("/_next") || pathname.startsWith("/api") || pathname.startsWith("/files") || pathname.includes(".")) {
    return NextResponse.next();
  }

  // Check for auth cookie
  const token = request.cookies.get(COOKIE_NAME);
  if (!token) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
