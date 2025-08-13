'use client';
import React, { useEffect, useState } from 'react';
import { getVersion } from '../../services/api';
import TopBar from '../../components/TopBar';

import GoogleAppPasswordHelp from '../../components/help/GoogleAppPasswordHelp';
import SettingsSidebar from '../../components/settings/SettingsSidebar';
import ImapSettings from '../../components/settings/ImapSettings';
import McpServersSettings from '../../components/settings/McpServersSettings';
import BalanceSettings from '../../components/settings/BalanceSettings';

const SettingsPage = () => {
  const [version, setVersion] = useState<string>('');
  const [isHelpPanelOpen, setHelpPanelOpen] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('imap');

  useEffect(() => {
    const fetchVersion = async () => {
      const fetchedVersion = await getVersion();
      setVersion(fetchedVersion);
    };
    fetchVersion();

    // Parse query params for tab/topup
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const tab = params.get('tab');
      const topup = params.get('topup');
      if (tab === 'balance') {
        setSelectedCategory('balance');
      }
      if (topup === 'success') {
        // Basic banner via alert for now; BalanceSettings will refetch on mount
        setTimeout(() => alert('Top-up successful!\n\nSomething went wrong? Please contact us at founders@itempass.com!'), 0);
      } else if (topup === 'cancel') {
        setTimeout(() => alert('Top-up canceled.\n\nSomething went wrong? Please contact us at founders@itempass.com!'), 0);
      }
    }
  }, []);
  
  return (
    <div className="flex flex-col h-screen relative bg-gray-100" style={{
      backgroundImage: 'radial-gradient(#E5E7EB 1px, transparent 1px)',
      backgroundSize: '24px 24px'
    }}>
      <TopBar />
      <div className="flex flex-1 overflow-hidden gap-4 p-4">
        <div className="w-64 flex-shrink-0 flex flex-col bg-white border border-gray-300 rounded-lg overflow-hidden shadow-md">
            <SettingsSidebar 
                version={version} 
                selectedCategory={selectedCategory}
                setSelectedCategory={setSelectedCategory}
            />
        </div>
        
        <div className="flex-1 bg-white border border-gray-300 rounded-lg shadow-md overflow-y-auto">
            {selectedCategory === 'imap' && (
                <ImapSettings 
                    setHelpPanelOpen={setHelpPanelOpen}
                />
            )}
            {selectedCategory === 'mcp' && <McpServersSettings />}
            {selectedCategory === 'balance' && <BalanceSettings />}
        </div>

        {isHelpPanelOpen && (
            <div className="w-full max-w-2xl bg-white border border-gray-300 rounded-lg shadow-md overflow-y-auto">
                <GoogleAppPasswordHelp onClose={() => setHelpPanelOpen(false)} />
            </div>
        )}
      </div>
    </div>
  );
};

export default SettingsPage; 