'use client';

import { Auth0Provider as Provider } from '@auth0/nextjs-auth0';
import React from 'react';

export default function Auth0Provider({ children }: { children: React.ReactNode }) {
  return <Provider>{children}</Provider>;
} 