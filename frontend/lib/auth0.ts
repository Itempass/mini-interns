import { Auth0Client } from "@auth0/nextjs-auth0/server";
import { NextRequest } from "next/server";

export const getAuth0Client = (request: NextRequest) => {
  const host = request.headers.get('host');
  const protocol = request.nextUrl.protocol.replace(/:$/, '');
  const appBaseUrl = `${protocol}://${host}`;

  return new Auth0Client({
    appBaseUrl: appBaseUrl,
    authorizationParameters: {
      audience: process.env.NEXT_PUBLIC_AUTH0_AUDIENCE,
    },
    routes: {
      login: '/auth-client/login',
      callback: '/auth-client/callback',
      logout: '/auth-client/logout'
    }
  });
}; 