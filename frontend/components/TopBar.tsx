'use client';
import React, { useState, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import VersionCheck from './VersionCheck';
import { getClientAuthMode, getMe, UserProfile } from '../services/api';
import { Github } from 'lucide-react';

interface TopBarProps {}

const TopBar: React.FC<TopBarProps> = () => {
  const router = useRouter();
  const pathname = usePathname();
  const [authMode, setAuthMode] = useState<'auth0' | 'password' | 'none' | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);

  useEffect(() => {
    getClientAuthMode().then(setAuthMode);
    getMe().then(setUser);
  }, []);
  
  const activeView = pathname === '/logs' ? 'logs' : pathname === '/settings' ? 'settings' : pathname === '/management' ? 'management' : 'agent';

  const getButtonClasses = (view: 'agent' | 'settings' | 'logs' | 'management') => {
    const baseClasses = "py-1.5 px-3 border-2 rounded cursor-pointer text-sm font-bold transition-all duration-200 ease-in-out";
    if (activeView === view) {
      return `${baseClasses} bg-gradient-to-b from-gray-800 to-black text-white border-black shadow-lg`;
    }
    return `${baseClasses} bg-white text-black border-black hover:bg-gray-50`;
  };

  return (
    <div className="bg-transparent px-10 pt-7 pb-3 flex justify-between items-center">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full border-2 border-black flex items-center justify-center bg-transparent">
          <span className="text-black font-bold text-sm">B</span>
        </div>
        <h1 className="text-gray-900 text-xl font-bold m-0">Brewdock - The opensource Agent Factory</h1>
        <VersionCheck />
      </div>
      <nav className="flex items-center gap-2">
        <button
          className={getButtonClasses('agent')}
          onClick={() => router.push('/workflows')}
        >
          Workflows
        </button>
        {user?.is_admin && (
            <button
                className={getButtonClasses('management')}
                onClick={() => router.push('/management')}
            >
                Management
            </button>
        )}
        <button
          className={getButtonClasses('logs')}
          onClick={() => router.push('/logs')}
        >
          Logs
        </button>
        <button
          className={getButtonClasses('settings')}
          onClick={() => router.push('/settings')}
        >
          Settings
        </button>
        {authMode === 'auth0' && (
          <>
            <div className="border-l border-gray-300 h-6"></div>
            <a
              href="/auth-client/logout"
              className="py-1.5 px-3 border-2 rounded cursor-pointer text-sm font-bold transition-all duration-200 ease-in-out bg-white text-black border-black hover:bg-gray-50 flex items-center gap-2"
            >
              Logout
            </a>
          </>
        )}
        <div className="border-l border-gray-300 h-6"></div>
        <a
          href="https://github.com/Itempass/brewdock"
          target="_blank"
          rel="noopener noreferrer"
          className="py-1.5 px-3 border-2 rounded cursor-pointer text-sm font-bold transition-all duration-200 ease-in-out bg-white text-black border-black hover:bg-gray-50 flex items-center gap-2"
        >
          <Github size={16} />
          Star us on Github
        </a>
      </nav>
    </div>
  );
};

export default TopBar; 