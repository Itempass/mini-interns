'use client';
import React from 'react';
import { useRouter, usePathname } from 'next/navigation';

interface TopBarProps {}

const TopBar: React.FC<TopBarProps> = () => {
  const router = useRouter();
  const pathname = usePathname();
  
  const activeView = pathname === '/logs' ? 'logs' : 'settings';
  const topBarStyle: React.CSSProperties = {
    backgroundColor: '#007bff',
    padding: '16px 40px',
    marginBottom: '0',
    borderBottom: '1px solid #0056b3',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  };

  const titleStyle: React.CSSProperties = {
    color: 'white',
    fontSize: '24px',
    fontWeight: 'bold',
    margin: 0,
  };

  const navStyle: React.CSSProperties = {
    display: 'flex',
    gap: '12px',
  };

  const buttonBaseStyle: React.CSSProperties = {
    padding: '8px 16px',
    border: '2px solid white',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '16px',
    fontWeight: 'bold',
    transition: 'all 0.2s ease',
  };

  const activeButtonStyle: React.CSSProperties = {
    ...buttonBaseStyle,
    backgroundColor: 'white',
    color: '#007bff',
  };

  const inactiveButtonStyle: React.CSSProperties = {
    ...buttonBaseStyle,
    backgroundColor: 'transparent',
    color: 'white',
  };

  return (
    <div style={topBarStyle}>
      <h1 style={titleStyle}>Mini Interns Dashboard</h1>
      <nav style={navStyle}>
        <button
          style={activeView === 'settings' ? activeButtonStyle : inactiveButtonStyle}
          onClick={() => router.push('/')}
        >
          Settings
        </button>
        <button
          style={activeView === 'logs' ? activeButtonStyle : inactiveButtonStyle}
          onClick={() => router.push('/logs')}
        >
          Logs
        </button>
      </nav>
    </div>
  );
};

export default TopBar; 