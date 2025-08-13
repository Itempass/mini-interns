'use client';
import React, { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { getClientAuthMode, getMe, UserProfile } from '../services/api';

const GlobalBalanceBanner: React.FC = () => {
  const [authMode, setAuthMode] = useState<'auth0' | 'password' | 'none'>('none');
  const [user, setUser] = useState<UserProfile | null>(null);
  const pathname = usePathname();

  const load = async () => {
    const mode = await getClientAuthMode();
    setAuthMode(mode);
    if (mode === 'auth0') {
      const me = await getMe();
      setUser(me);
    } else {
      setUser(null);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        load();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (authMode !== 'auth0' || !user || typeof user.balance !== 'number' || user.balance >= 2) {
    return null;
  }

  return (
    <div className="w-full bg-yellow-50 border-b border-yellow-200 text-yellow-900 text-sm px-4 py-2 flex items-center justify-center z-40">
      <span>
        Your balance is low (${user.balance.toFixed(2)}). Top up to avoid interruptions.
      </span>
      <a href="/settings?tab=balance" className="ml-3 underline font-semibold">Top up now</a>
    </div>
  );
};

export default GlobalBalanceBanner;


