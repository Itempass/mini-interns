'use client';
import React, { useState, useEffect } from 'react';
import { getSettings, setSettings, AppSettings, initializeInbox, getInboxInitializationStatus, testImapConnection, reinitializeInbox, getVersion } from '../../services/api';
import { Copy } from 'lucide-react';
import TopBar from '../../components/TopBar';
import VersionCheck from '../../components/VersionCheck';

const SettingsPage = () => {
  const [settings, setSettingsState] = useState<AppSettings>({});
  const [initialSettings, setInitialSettings] = useState<AppSettings>({});
  const [inboxStatus, setInboxStatus] = useState<string | null>(null);
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle');
  const [testMessage, setTestMessage] = useState<string>('');
  const [version, setVersion] = useState<string>('');

  const hasUnsavedChanges = JSON.stringify(settings) !== JSON.stringify(initialSettings);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {}, (err) => {
      console.error('Failed to copy text: ', err);
    });
  };

  const copyButtonStyle = "bg-gray-100 border border-gray-300 rounded-full w-6 h-6 flex items-center justify-center cursor-pointer ml-2";

  useEffect(() => {
    console.log('Component mounted. Fetching initial data.');
    const fetchSettings = async () => {
      const fetchedSettings = await getSettings();
      setSettingsState(fetchedSettings);
      setInitialSettings(fetchedSettings);
    };
    const fetchVersion = async () => {
        const fetchedVersion = await getVersion();
        setVersion(fetchedVersion);
    }
    fetchSettings();
    fetchVersion();
  }, []);

  useEffect(() => {
    const fetchStatus = async () => {
      const status = await getInboxInitializationStatus();
      setInboxStatus(status);
      return status;
    };

    fetchStatus(); // Initial fetch

    const interval = setInterval(async () => {
      const status = await fetchStatus();
      if (status === 'completed' || status === 'failed') {
        clearInterval(interval);
      }
    }, 5000); // Poll every 5 seconds

    return () => clearInterval(interval); // Cleanup on unmount
  }, []);

  const handleSave = async () => {
    console.log('Save button clicked. Saving settings:', settings);
    await setSettings(settings);
    setInitialSettings(settings);
    alert('Settings saved!');
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setSettingsState(prev => ({ ...prev, [name]: value }));
  };

  const handleTestConnection = async () => {
    if (hasUnsavedChanges) {
        if (!window.confirm('You have unsaved changes that will not be included in the test. Please save your settings first. Do you want to proceed anyway?')) {
            return;
        }
    }
    setTestStatus('testing');
    setTestMessage('');
    try {
      const result = await testImapConnection();
      setTestStatus('success');
      setTestMessage(result.message);
    } catch (error: any) {
      setTestStatus('error');
      setTestMessage(error.message || 'An unknown error occurred.');
    }
  };

  const handleVectorize = async () => {
    await initializeInbox();
    const status = await getInboxInitializationStatus();
    setInboxStatus(status);
  };

  const handleRevectorize = async () => {
    if (window.confirm('Are you sure you want to re-vectorize? This will delete all existing email vector data and start from scratch. This action cannot be undone.')) {
      await reinitializeInbox();
      const status = await getInboxInitializationStatus();
      setInboxStatus(status);
    }
  };

  const getStatusClasses = (status: string | null): string => {
    const baseClasses = 'font-bold';
    switch (status) {
      case 'running':
        return `${baseClasses} text-yellow-500`;
      case 'completed':
        return `${baseClasses} text-green-500`;
      case 'failed':
      case 'not_started':
        return `${baseClasses} text-red-500`;
      default:
        return baseClasses;
    }
  };
  
  const settingsSectionClasses = "border border-gray-300 p-4 mb-5 rounded-lg bg-gray-50";
  const settingRowClasses = "flex items-center mb-3";
  const labelClasses = "mr-2 w-48 text-right font-bold";
  const inputClasses = "w-full p-2 rounded border border-gray-300 box-border";
  const buttonClasses = "py-2 px-5 border-none rounded bg-blue-500 text-white cursor-pointer text-base block mx-auto";

  return (
    <div>
      <VersionCheck />
      <TopBar />
      <div className="p-10 max-w-4xl mx-auto font-sans">
        <div className={settingsSectionClasses}>
          <h2 className="text-center mb-5 text-2xl font-bold">Inbox Vectorization</h2>
          <p className="text-center text-sm text-gray-600 mb-5">
            To enable semantic search over your emails, they need to be vectorized and stored. This process can take a few minutes.
          </p>
          <div className="text-center mb-5">
            <span>Inbox Vectorization Status: </span>
            <span className={getStatusClasses(inboxStatus)}>
              {inboxStatus ? inboxStatus.charAt(0).toUpperCase() + inboxStatus.slice(1).replace('_', ' ') : 'Loading...'}
            </span>
          </div>
          <div className="flex justify-center items-center space-x-4">
            <button className={buttonClasses.replace('block mx-auto', '')} onClick={handleVectorize}>Start Inbox Vectorization</button>
            <button className={`${buttonClasses.replace('block mx-auto', '')} bg-amber-600`} onClick={handleRevectorize}>Re-vectorize Inbox</button>
          </div>
        </div>
        <div className={settingsSectionClasses}>
          <h2 className="text-center mb-5 text-2xl font-bold">Connection Settings</h2>
          
          <div className={settingRowClasses}>
          <label className={labelClasses}>IMAP Server:</label>
          <div className="flex-1">
            <input className={inputClasses} type="text" id="imap-server" name="IMAP_SERVER" value={settings.IMAP_SERVER || ''} onChange={handleInputChange} />
            <div className="flex items-center mt-1">
              <p className="m-0 text-xs text-gray-600">example: imap.gmail.com</p>
              <button onClick={() => handleCopy('imap.gmail.com')} className={copyButtonStyle} title="Copy">
                <Copy size={14} />
              </button>
            </div>
          </div>
        </div>
        <div className={settingRowClasses}>
          <label className={labelClasses} htmlFor="imap-username">IMAP Username:</label>
          <div className="flex-1">
            <input className={inputClasses} type="text" id="imap-username" name="IMAP_USERNAME" value={settings.IMAP_USERNAME || ''} onChange={handleInputChange} />
            <div className="flex items-center mt-1">
              <p className="m-0 text-xs text-gray-600">example: your.email@gmail.com</p>
              <button onClick={() => handleCopy('your.email@gmail.com')} className={copyButtonStyle} title="Copy">
                <Copy size={14} />
              </button>
            </div>
          </div>
        </div>
        <div className={settingRowClasses}>
          <label className={labelClasses} htmlFor="imap-password">IMAP Password:</label>
          <div className="flex-1">
            <input className={inputClasses} type="password" id="imap-password" name="IMAP_PASSWORD" value={settings.IMAP_PASSWORD || ''} onChange={handleInputChange} />
          </div>
        </div>
        <div className={settingRowClasses}>
          <label className={labelClasses} htmlFor="openrouter-api-key">OpenRouter API Key:</label>
          <div className="flex-1">
            <input className={inputClasses} type="password" id="openrouter-api-key" name="OPENROUTER_API_KEY" value={settings.OPENROUTER_API_KEY || ''} onChange={handleInputChange} />
          </div>
        </div>
        <div className={settingRowClasses}>
          <label className={labelClasses} htmlFor="openrouter-model">OpenRouter Model:</label>
          <div className="flex-1">
            <div className="flex items-center">
              <input
                className={inputClasses}
                type="text"
                id="openrouter-model"
                name="OPENROUTER_MODEL"
                value={settings.OPENROUTER_MODEL || ''}
                onChange={handleInputChange}
              />
              <span
                title="copy the exact model slug from openrouter's website"
                className="ml-2 cursor-help text-xl text-gray-600"
              >
                &#9432;
              </span>
            </div>
            <div className="flex items-center mt-1">
              <p className="m-0 text-xs text-gray-600">example: google/gemini-2.5-flash-preview-05-20:thinking</p>
              <button onClick={() => handleCopy('google/gemini-2.5-flash-preview-05-20:thinking')} className={copyButtonStyle} title="Copy">
                <Copy size={14} />
              </button>
            </div>
          </div>
        </div>
        
        {testMessage && (
            <div className={`text-center p-2 mb-4 rounded-md text-sm ${testStatus === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                {testMessage}
            </div>
        )}
        <div className="flex justify-center items-center space-x-4">
          <button className={buttonClasses.replace('block mx-auto', '')} onClick={handleSave}>Save Settings</button>
          <button className={`${buttonClasses.replace('block mx-auto', '')} bg-gray-500`} onClick={handleTestConnection} disabled={testStatus === 'testing'}>
              {testStatus === 'testing' ? 'Testing...' : 'Test Connection'}
          </button>
        </div>
        <p className="text-center text-xs text-gray-500 mt-2">First save any new settings before testing.</p>
        </div>
        {version && <p className="text-center text-xs text-gray-400 mt-4">Version: {version}</p>}
      </div>
    </div>
  );
};

export default SettingsPage; 