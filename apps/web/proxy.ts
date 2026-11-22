/**
 * Next 16 Proxy (formerly Middleware): send signed-out visitors of the app to the
 * sign-in page. It only checks that the `dp_session` cookie is present; the API checks
 * the session on every call and answers 401, which the UI also handles.
 */
import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, signInRedirect } from "@/lib/api/proxy-rules";

export function proxy(request: NextRequest) {
  // Fixture mode serves canned data without the API, so there is no session to check.
  if (process.env.NEXT_PUBLIC_API_MODE === "fixtures") return NextResponse.next();
  const { pathname, search } = request.nextUrl;
  const target = signInRedirect(pathname, search, request.cookies.has(SESSION_COOKIE));
  if (target === null) return NextResponse.next();
  return NextResponse.redirect(new URL(target, request.url));
}

export const config = {
  // Keep in sync with PROTECTED_PREFIXES in lib/api/proxy-rules.ts.
  matcher: ["/app/:path*", "/cases/:path*", "/discover/:path*", "/investors/:path*"],
};
