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
  const { pathname } = request.nextUrl;
  
  // Pass-through for API routes and static files
  if (pathname.startsWith('/api') || pathname.startsWith('/_next')) {
    return NextResponse.next();
  }

  // Environment variables are available in middleware
  const isSelfSet = process.env.AUTH_SELFSET_PASSWORD === 'true';
  const legacyPassword = process.env.AUTH_PASSWORD;
  const authCookieName = getAuthCookieName(isSelfSet);

  let authStatus: AuthStatus;

  if (isSelfSet) {
    // In self-set mode, we MUST query the backend to know if a password has been created.
    // The request to /api/auth/status is excluded by the matcher config and won't loop.
    const statusResponse = await fetch(new URL('/api/auth/status', request.url));
    if (statusResponse.ok) {
      const data = await statusResponse.json();
      authStatus = data.status;
    } else {
      // If the backend is down, we can't determine status. 
      // We can show a generic error or let it fail. For now, we'll treat as unconfigured.
      authStatus = 'unconfigured';
    }
  } else {
    authStatus = legacyPassword ? 'legacy_configured' : 'unconfigured';
  }
  
  const isConfigured = authStatus === 'legacy_configured' || authStatus === 'self_set_configured';
  const needsSetup = authStatus === 'self_set_unconfigured';

  const sessionCookie = request.cookies.get(authCookieName);
  const loginUrl = new URL('/login', request.url);
  const setupUrl = new  URL('/set-password', request.url);
  const homeUrl = new URL('/', request.url);


  // State 1: Application needs initial password setup
  if (needsSetup) {
    if (pathname !== '/set-password') {
      return NextResponse.redirect(setupUrl);
    }
    return NextResponse.next();
  }

  // State 2: Application is not configured and not in self-set mode. No protection.
  if (!isConfigured) {
    return NextResponse.next();
  }

  // State 3: Application is configured. Protect all routes.
  const password = isSelfSet ? '' : legacyPassword; // For legacy, we need password to validate token.

  // If there's no cookie, redirect to login.
  if (!sessionCookie) {
    if (pathname !== '/login') {
      return NextResponse.redirect(loginUrl);
    }
    return NextResponse.next();
  }

  // If there IS a cookie, validate it.
  if (isSelfSet) {
    // In self-set mode, we MUST ask the backend to verify the token, as only
    // the backend knows the current password to validate the signature.
    const verifyUrl = new URL('/api/auth/verify', request.url);
    const verifyResponse = await fetch(verifyUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: sessionCookie.value }),
    });

    if (verifyResponse.ok) {
        const data = await verifyResponse.json();
        if (data.valid !== true) {
            // The cookie is invalid (e.g., password changed). Delete it and redirect to login.
            const response = NextResponse.redirect(loginUrl);
            response.cookies.delete(authCookieName);
            return response;
        }
    } else {
        // If the verify endpoint fails, invalidate the session for security.
        const response = NextResponse.redirect(loginUrl);
        response.cookies.delete(authCookieName);
        return response;
    }

  } else if (password) {
    // For legacy mode, we can validate the token directly in the middleware.
    const expectedToken = await get_session_token(password);
    if (sessionCookie.value !== expectedToken) {
      // The cookie is invalid. Redirect to login and delete the bad cookie.
      const response = NextResponse.redirect(loginUrl);
      response.cookies.delete(authCookieName);
      return response;
    }
  }
  
  // The cookie is valid.
  // If the user tries to access login or setup, redirect them to the home page.
  if (pathname === '/login' || pathname === '/set-password') {
    return NextResponse.redirect(homeUrl);
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