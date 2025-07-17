'use client';
import React from 'react';
import { useRouter, usePathname } from 'next/navigation';
import VersionCheck from './VersionCheck';

interface TopBarProps {}

const TopBar: React.FC<TopBarProps> = () => {
  const router = useRouter();
  const pathname = usePathname();
  
  const activeView = pathname === '/logs' ? 'logs' : pathname === '/settings' ? 'settings' : 'agent';

  const getButtonClasses = (view: 'agent' | 'settings' | 'logs') => {
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
        <h1 className="text-gray-900 text-xl font-bold m-0">Brewdock - The AI Agent Factory</h1>
        <VersionCheck />
      </div>
      <nav className="flex gap-2">
        <button
          className={getButtonClasses('agent')}
          onClick={() => router.push('/workflows')}
        >
          Workflows
        </button>
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
      </nav>
    </div>
  );
};

export default TopBar; 