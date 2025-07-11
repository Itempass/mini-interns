import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { getAuthStatus, AuthStatus } from './services/api';

// This salt must be the same as the one in the Python backend.
const SESSION_SALT = "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890";

function getAuthCookieName(isSelfSet: boolean): string {
    return isSelfSet 
        ? "min_interns_auth_session_selfset" 
        : "min_interns_auth_session_legacy";
}

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
  console.log(`[MIDDLEWARE] Request for: ${request.url}`);
  const { pathname } = request.nextUrl;
  console.log(`[MIDDLEWARE] Pathname: ${pathname}`);
  
  // Pass-through for API routes and static files
  if (pathname.startsWith('/api') || pathname.startsWith('/_next')) {
    console.log('[MIDDLEWARE] Passing through for API or _next route.');
    return NextResponse.next();
  }

  // Environment variables are available in middleware
  const isSelfSet = process.env.AUTH_SELFSET_PASSWORD === 'true';
  const legacyPassword = process.env.AUTH_PASSWORD;
  const authCookieName = getAuthCookieName(isSelfSet);
  console.log(`[MIDDLEWARE] isSelfSet: ${isSelfSet}, authCookieName: ${authCookieName}`);

  let authStatus: AuthStatus;

  if (isSelfSet) {
    console.log('[MIDDLEWARE] Self-set mode enabled. Querying backend for status.');
    // In self-set mode, we MUST query the backend to know if a password has been created.
    const apiUrl = `http://127.0.0.1:${process.env.CONTAINERPORT_API}`;
    const statusUrl = `${apiUrl}/auth/status`;
    console.log(`[MIDDLEWARE] Fetching auth status from: ${statusUrl}`);

    const statusResponse = await fetch(statusUrl);
    console.log(`[MIDDLEWARE] Auth status response status: ${statusResponse.status}`);

    if (statusResponse.ok) {
      const data = await statusResponse.json();
      authStatus = data.status;
      console.log(`[MIDDLEWARE] Auth status from backend: ${authStatus}`);
    } else {
      // If the backend is down or returns an error, we can't determine status.
      // Throwing an error here will prevent access, acting as a "fail closed" mechanism.
      throw new Error(`Backend status check failed with status: ${statusResponse.status}`);
    }
  } else {
    authStatus = legacyPassword ? 'legacy_configured' : 'unconfigured';
    console.log(`[MIDDLEWARE] Legacy mode. Auth status: ${authStatus}`);
  }
  
  const isConfigured = authStatus === 'legacy_configured' || authStatus === 'self_set_configured';
  const needsSetup = authStatus === 'self_set_unconfigured';
  console.log(`[MIDDLEWARE] isConfigured: ${isConfigured}, needsSetup: ${needsSetup}`);

  const sessionCookie = request.cookies.get(authCookieName);
  const loginUrl = new URL('/login', request.url);
  const setupUrl = new  URL('/set-password', request.url);
  const homeUrl = new URL('/', request.url);


  // State 1: Application needs initial password setup
  if (needsSetup) {
    if (pathname !== '/set-password') {
      console.log('[MIDDLEWARE] Needs setup. Redirecting to /set-password.');
      return NextResponse.redirect(setupUrl);
    }
    console.log('[MIDDLEWARE] Needs setup. Already on /set-password. Allowing.');
    return NextResponse.next();
  }

  // State 2: Application is not configured and not in self-set mode. No protection.
  if (!isConfigured) {
    console.log('[MIDDLEWARE] Not configured. Allowing access.');
    return NextResponse.next();
  }

  // State 3: Application is configured. Protect all routes.
  const password = isSelfSet ? '' : legacyPassword; // For legacy, we need password to validate token.

  // If there's no cookie, redirect to login.
  if (!sessionCookie) {
    if (pathname !== '/login') {
      console.log('[MIDDLEWARE] No session cookie. Redirecting to /login.');
      return NextResponse.redirect(loginUrl);
    }
    console.log('[MIDDLEWARE] No session cookie. Already on /login. Allowing.');
    return NextResponse.next();
  }
  console.log('[MIDDLEWARE] Session cookie found.');

  // If there IS a cookie, validate it.
  if (isSelfSet) {
    console.log('[MIDDLEWARE] Self-set mode. Verifying session cookie with backend.');
    // In self-set mode, we MUST ask the backend to verify the token.
    const apiUrl = `http://127.0.0.1:${process.env.CONTAINERPORT_API}`;
    const verifyUrl = `${apiUrl}/auth/verify`;
    console.log(`[MIDDLEWARE] Verifying token at: ${verifyUrl}`);

    const verifyResponse = await fetch(verifyUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: sessionCookie.value }),
    });
    console.log(`[MIDDLEWARE] Verify response status: ${verifyResponse.status}`);

    if (verifyResponse.ok) {
        const data = await verifyResponse.json();
        if (data.valid !== true) {
            console.log('[MIDDLEWARE] Token invalid. Deleting cookie and redirecting to /login.');
            const response = NextResponse.redirect(loginUrl);
            response.cookies.delete(authCookieName);
            return response;
        }
        console.log('[MIDDLEWARE] Token is valid.');
    } else {
        console.log('[MIDDLEWARE] Verify endpoint returned non-ok status. Deleting cookie and redirecting to /login.');
        const response = NextResponse.redirect(loginUrl);
        response.cookies.delete(authCookieName);
        return response;
    }
  } else if (password) {
    console.log('[MIDDLEWARE] Legacy mode. Verifying session cookie in middleware.');
    // For legacy mode, we can validate the token directly in the middleware.
    const expectedToken = await get_session_token(password);
    if (sessionCookie.value !== expectedToken) {
      console.log('[MIDDLEWARE] Legacy token invalid. Deleting cookie and redirecting to /login.');
      // The cookie is invalid. Redirect to login and delete the bad cookie.
      const response = NextResponse.redirect(loginUrl);
      response.cookies.delete(authCookieName);
      return response;
    }
    console.log('[MIDDLEWARE] Legacy token valid.');
  }
  
  // The cookie is valid.
  // If the user tries to access login or setup, redirect them to the home page.
  if (pathname === '/login' || pathname === '/set-password') {
    console.log('[MIDDLEWARE] User is authenticated. Redirecting from login/setup to home.');
    return NextResponse.redirect(homeUrl);
  }

  // Otherwise, allow them to proceed.
  console.log('[MIDDLEWARE] User is authenticated. Allowing access.');
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