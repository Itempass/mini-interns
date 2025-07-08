import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export const AUTH_COOKIE_NAME = "min_interns_auth_session";

// This salt must be the same as the one in the Python backend.
const SESSION_SALT = "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890";

async function get_session_token(password: string): Promise<string> {
  const token_source = `${SESSION_SALT}-${password}`;
  const te = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    te.encode(SESSION_SALT),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signature = await crypto.subtle.sign("HMAC", key, te.encode(token_source));
  
  // Convert ArrayBuffer to hex string
  return Array.from(new Uint8Array(signature)).map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const password = process.env.AUTH_PASSWORD;

  // If authentication is not enabled, do nothing.
  if (!password) {
    return NextResponse.next();
  }

  const sessionCookie = request.cookies.get(AUTH_COOKIE_NAME);

  // If there's no cookie, redirect to login.
  if (!sessionCookie) {
    if (pathname !== '/login') {
      return NextResponse.redirect(new URL('/login', request.url));
    }
    return NextResponse.next();
  }

  // If there IS a cookie, validate it.
  const expectedToken = await get_session_token(password);
  
  // Using a simple equality check is fine here, as the source of expectedToken is secure.
  if (sessionCookie.value !== expectedToken) {
    // The cookie is invalid. Redirect to login and delete the bad cookie.
    const response = NextResponse.redirect(new URL('/login', request.url));
    response.cookies.delete(AUTH_COOKIE_NAME);
    return response;
  }
  
  // The cookie is valid.
  // If the user tries to access the login page, redirect them to the home page.
  if (pathname === '/login') {
    return NextResponse.redirect(new URL('/', request.url));
  }

  // Otherwise, allow them to proceed.
  return NextResponse.next();
}

// See "Matching Paths" below to learn more
export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!api|_next/static|_next/image|favicon.ico).*)',
  ],
} 