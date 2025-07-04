'use client';
import React from 'react';
import { useRouter, usePathname } from 'next/navigation';

interface TopBarProps {}

const TopBar: React.FC<TopBarProps> = () => {
  const router = useRouter();
  const pathname = usePathname();
  
  const activeView = pathname === '/logs' ? 'logs' : pathname === '/settings' ? 'settings' : 'agent';

  const getButtonClasses = (view: 'agent' | 'settings' | 'logs') => {
    const baseClasses = "py-2 px-4 border-2 border-white rounded cursor-pointer text-base font-bold transition-all duration-200 ease-in-out";
    if (activeView === view) {
      return `${baseClasses} bg-white text-blue-500`;
    }
    return `${baseClasses} bg-transparent text-white`;
  };

  return (
    <div className="bg-blue-500 px-10 py-4 flex justify-between items-center border-b border-blue-700">
      <h1 className="text-white text-2xl font-bold m-0">Mini Interns Dashboard</h1>
      <nav className="flex gap-3">
        <button
          className={getButtonClasses('agent')}
          onClick={() => router.push('/')}
        >
          Agents
        </button>
        <button
          className={getButtonClasses('settings')}
          onClick={() => router.push('/settings')}
        >
          Settings
        </button>
        <button
          className={getButtonClasses('logs')}
          onClick={() => router.push('/logs')}
        >
          Logs
        </button>
      </nav>
    </div>
  );
};

export default TopBar; 