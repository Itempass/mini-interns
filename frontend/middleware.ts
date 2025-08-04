import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { getAuth0Client } from './lib/auth0';

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

// This is the main middleware handler
export default async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const auth0 = getAuth0Client(request);
  
  // Always allow API routes and static files to pass through
  if (pathname.startsWith('/api') || pathname.startsWith('/_next')) {
    return NextResponse.next();
  }

  // If the request is for an Auth0 route, delegate to the Auth0 middleware directly
  if (pathname.startsWith('/auth-client/')) {
    return await auth0.middleware(request);
  }

  // Fetch the auth mode from the backend
  const apiUrl = process.env.NEXT_PUBLIC_API_BASE_URL || `http://127.0.0.1:${process.env.CONTAINERPORT_API}`;
  const modeUrl = `${apiUrl}/auth/mode`;
  
  try {
    const modeResponse = await fetch(modeUrl);
    if (!modeResponse.ok) throw new Error('Failed to fetch auth mode');
    
    const { mode } = await modeResponse.json();

    switch (mode) {
      case 'auth0': {
        const { pathname } = request.nextUrl;

        // The login page and the Auth0 client routes are public and should not be protected.
        // This check prevents the redirect loop.
        if (pathname === '/login' || pathname.startsWith('/auth-client/')) {
          return auth0.middleware(request);
        }

        // For all other routes, check for a session.
        const session = await auth0.getSession(request);

        if (!session) {
          // If no session exists, redirect to the login page.
          return NextResponse.redirect(new URL('/login', request.url));
        }

        // If a session exists, proceed with the response from the Auth0 middleware.
        return await auth0.middleware(request);
      }
      
      case 'password':
        // In password mode, run the legacy password-checking logic
        return await handlePasswordAuth(request, apiUrl);
        
      case 'none':
      default:
        // In "none" mode, or if the mode is unrecognized, allow access
        return NextResponse.next();
    }
  } catch (error) {
    console.error("Could not fetch auth mode from backend. The API might be down.", error);
    return new NextResponse('Could not connect to authentication service.', { status: 503 });
  }
}


// --- Helper function for the legacy password logic ---
async function handlePasswordAuth(request: NextRequest, apiUrl: string) {
    const { pathname } = request.nextUrl;
    
    const isSelfSet = process.env.AUTH_SELFSET_PASSWORD === 'true';
    const legacyPassword = process.env.AUTH_PASSWORD;
    const authCookieName = getAuthCookieName(isSelfSet);
    
    let authStatus;
    if (isSelfSet) {
        const statusUrl = `${apiUrl}/auth/status`;
        const statusResponse = await fetch(statusUrl);
        if (statusResponse.ok) {
            const data = await statusResponse.json();
            authStatus = data.status;
        } else {
            throw new Error(`Backend status check failed: ${statusResponse.status}`);
        }
    } else {
        authStatus = legacyPassword ? 'legacy_configured' : 'unconfigured';
    }

    const needsSetup = authStatus === 'self_set_unconfigured';
    const loginUrl = new URL('/login', request.url);
    const setupUrl = new URL('/set-password', request.url);

    if (needsSetup) {
        if (pathname !== '/set-password') return NextResponse.redirect(setupUrl);
        return NextResponse.next();
    }

    const sessionCookie = request.cookies.get(authCookieName);
    if (!sessionCookie) {
        if (pathname !== '/login') return NextResponse.redirect(loginUrl);
        return NextResponse.next();
    }

    if (isSelfSet) {
        const verifyUrl = `${apiUrl}/auth/verify`;
        const verifyResponse = await fetch(verifyUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: sessionCookie.value }),
        });
        if (verifyResponse.ok) {
            const data = await verifyResponse.json();
            if (data.valid !== true) {
                const response = NextResponse.redirect(loginUrl);
                response.cookies.delete(authCookieName);
                return response;
            }
        } else {
            const response = NextResponse.redirect(loginUrl);
            response.cookies.delete(authCookieName);
            return response;
        }
    } else if (legacyPassword) {
        const expectedToken = await get_session_token(legacyPassword);
        if (sessionCookie.value !== expectedToken) {
            const response = NextResponse.redirect(loginUrl);
            response.cookies.delete(authCookieName);
            return response;
        }
    }

    if (pathname === '/login' || pathname === '/set-password') {
        return NextResponse.redirect(new URL('/', request.url));
    }

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