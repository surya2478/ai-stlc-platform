import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("access_token")?.value;
  const refreshToken = request.cookies.get("refresh_token")?.value;

  const { pathname } = request.nextUrl;

  // Paths that are publicly accessible. `/brand` holds the logo artwork: it is
  // not protected content, it has to render on the login screen, and without
  // it here every brand asset 307s to /login for a signed-out visitor.
  const publicPaths = ["/login", "/favicon.ico", "/login_bg.png", "/brand", "/api"];

  // Check if request is for a public path
  const isPublic = publicPaths.some((path) => pathname.startsWith(path));

  // If no auth tokens and path is not public, redirect to login page
  if (!token && !refreshToken && !isPublic && pathname !== "/") {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

// Match all pathnames except for Next.js internal folders and static assets
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
