import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const backendUrl = `http://127.0.0.1:${process.env.CONTAINERPORT_API}`;
const PROXY_TIMEOUT_MS = 300000; // 5 minutes

async function handler(req: NextRequest) {
  const originalUrl = req.nextUrl.pathname;
  // Correctly strip the `/api` prefix from the path
  const path = originalUrl.replace('/api', '');
  const url = `${backendUrl}${path}${req.nextUrl.search}`;

  console.log(`[API Proxy] Rerouting request from ${originalUrl} to ${url}`);

  // Forward headers, removing the host header
  const headers = new Headers(req.headers);
  headers.delete('host');

  try {
    // Make the request to the backend with a 5-minute timeout
    const response = await fetch(url, {
      method: req.method,
      headers,
      body: req.body,
      // @ts-ignore
      duplex: 'half', // Required for streaming request bodies
      signal: AbortSignal.timeout(PROXY_TIMEOUT_MS), // 5 minute timeout
    });

    // Copy headers from the backend response to the new response
    const responseHeaders = new Headers(response.headers);
    
    // Return a new response with the body and headers from the backend
    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error('[API Proxy Error]:', error);
    return new NextResponse('Proxy error', { status: 500 });
  }
}

export { handler as GET, handler as POST, handler as PUT, handler as DELETE, handler as PATCH }; 