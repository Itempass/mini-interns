import { Auth0Client } from "@auth0/nextjs-auth0/server";

const hostPort = process.env.HOSTPORT_FRONTEND || '3000';
const appBaseUrl = `http://localhost:${hostPort}`;

export const auth0 = new Auth0Client({
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