'use client';
import React, { useState, useEffect } from 'react';
import { getSettings, setSettings, AppSettings, EmbeddingModel, initializeInbox, getInboxInitializationStatus, testImapConnection, reinitializeInbox, getVersion } from '../../services/api';
import { Copy } from 'lucide-react';
import TopBar from '../../components/TopBar';
import VersionCheck from '../../components/VersionCheck';
import Link from 'next/link';
import GoogleAppPasswordHelp from '../../components/help/GoogleAppPasswordHelp';

const SettingsPage = () => {
  const [settings, setSettingsState] = useState<AppSettings>({});
  const [initialSettings, setInitialSettings] = useState<AppSettings>({});
  const [embeddingModels, setEmbeddingModels] = useState<EmbeddingModel[]>([]);
  const [inboxStatus, setInboxStatus] = useState<string | null>(null);
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle');
  const [testMessage, setTestMessage] = useState<string>('');
  const [version, setVersion] = useState<string>('');
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [isHelpPanelOpen, setHelpPanelOpen] = useState(false);
  const [showEmbeddingModelSaved, setShowEmbeddingModelSaved] = useState(false);
  const [embeddingConfigError, setEmbeddingConfigError] = useState<string>('');

  const hasUnsavedChanges = JSON.stringify(settings) !== JSON.stringify(initialSettings);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {}, (err) => {
      console.error('Failed to copy text: ', err);
    });
  };

  const copyButtonStyle = "bg-gray-100 border border-gray-300 rounded-full w-6 h-6 flex items-center justify-center cursor-pointer ml-2";

  const attemptAutoVectorization = async (currentSettings: AppSettings) => {
    if (currentSettings.IMAP_SERVER && currentSettings.IMAP_USERNAME && currentSettings.IMAP_PASSWORD) {
      try {
        // Test the connection with the provided settings.
        // The backend uses the saved settings, which have just been updated or fetched.
        await testImapConnection();
        
        const status = await getInboxInitializationStatus();
        if (status === 'not_started' || status === 'failed') {
          console.log(`Inbox status is '${status}', starting automatic vectorization.`);
          await initializeInbox();
          // The polling interval will update the status on the page.
        }
      } catch (error) {
        console.error("Automatic vectorization check failed: IMAP connection test was unsuccessful.", error);
        // Do not proceed with vectorization if credentials are bad.
        // User can use the manual "Test Connection" button for explicit feedback.
      }
    }
  };

  useEffect(() => {
    console.log('Component mounted. Fetching initial data.');
    const fetchSettings = async () => {
      const { settings: fetchedSettings, embeddingModels: fetchedModels } = await getSettings();
      setSettingsState(fetchedSettings);
      setInitialSettings(fetchedSettings);
      setEmbeddingModels(fetchedModels);

      if (!fetchedSettings.EMBEDDING_MODEL) {
        setEmbeddingConfigError("No embedding model configured. Please select a model to enable vectorization.");
      } else {
        setEmbeddingConfigError('');
      }

      await attemptAutoVectorization(fetchedSettings);
    };
    const fetchVersion = async () => {
        const fetchedVersion = await getVersion();
        setVersion(fetchedVersion);
    }
    fetchSettings();
    fetchVersion();
  }, []);

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (saveStatus === 'saved') {
      timer = setTimeout(() => {
        setSaveStatus('idle');
      }, 2000);
    }
    return () => clearTimeout(timer);
  }, [saveStatus]);

  useEffect(() => {
    if (showEmbeddingModelSaved) {
      const timer = setTimeout(() => {
        setShowEmbeddingModelSaved(false);
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [showEmbeddingModelSaved]);

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
    }, 3000); // Poll every 3 seconds

    return () => clearInterval(interval); // Cleanup on unmount
  }, []);

  const handleSave = async () => {
    console.log('Save button clicked. Saving settings:', settings);
    setSaveStatus('saving');
    await setSettings(settings);
    setInitialSettings(settings);
    setSaveStatus('saved');
    await attemptAutoVectorization(settings);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setSettingsState(prev => ({ ...prev, [name]: value }));
  };

  const handleEmbeddingModelChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newModelKey = e.target.value;
    const currentUIModelKey = settings.EMBEDDING_MODEL;
    const lastSavedModelKey = initialSettings.EMBEDDING_MODEL;

    // Do nothing if the model isn't actually changing from what's currently displayed
    if (newModelKey === currentUIModelKey) {
        return;
    }

    // Update the UI immediately to provide visual feedback.
    setSettingsState(prev => ({ ...prev, EMBEDDING_MODEL: newModelKey }));

    const selectedModel = embeddingModels.find(m => m.model_name_from_key === newModelKey);

    // If the new selection is invalid, show a warning and stop. The UI will show the invalid selection.
    if (!selectedModel || !selectedModel.api_key_provided) {
        return;
    }

    // If the user is selecting a valid model that is the same as the last saved one
    // (e.g., reverting an invalid choice), we don't need to save or re-vectorize.
    if (newModelKey === lastSavedModelKey) {
        setEmbeddingConfigError(''); // Clear any previous errors
        return;
    }

    // If we get here, the user is trying to switch to a NEW, VALID model.
    const confirmed = window.confirm(
        'Changing the embedding model requires re-vectorizing your entire inbox. This will delete all existing email vectors and can take several minutes. Are you sure you want to proceed?'
    );

    if (confirmed) {
        try {
            await setSettings({ EMBEDDING_MODEL: newModelKey });
            await reinitializeInbox();
            setInitialSettings(prev => ({ ...prev, EMBEDDING_MODEL: newModelKey }));
            setEmbeddingConfigError('');
        } catch (error) {
            console.error("Failed to update embedding model and re-vectorize:", error);
            setSettingsState(initialSettings); // Revert UI on failure
        }
    } else {
        // If the user cancels, revert the dropdown to its last saved state.
        setSettingsState(initialSettings);
    }
  };

  const handleTestConnection = async () => {
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

  const selectedEmbeddingModel = embeddingModels.find(m => m.model_name_from_key === settings.EMBEDDING_MODEL);
  
  return (
    <div className="flex flex-col h-screen">
      <VersionCheck />
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          <div className="p-10 max-w-4xl mx-auto font-sans">
            <div className={settingsSectionClasses}>
              <h2 className="text-center mb-5 text-2xl font-bold">Connection Settings</h2>
              <p className="text-center text-sm text-gray-600 mb-5">
                All settings are saved locally to your Docker Container. Your IMAP password is encrypted.
              </p>
              
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
                <div className="flex items-center mt-1">
                  <p className="m-0 text-xs text-gray-600">Enter your email password or an App Password. See help for more details.</p>
                  <button onClick={() => setHelpPanelOpen(true)} className="ml-2 text-xs text-blue-500 hover:underline">Help</button>
                </div>
              </div>
            </div>

            
            {testMessage && (
                <div className={`text-center p-2 mb-4 rounded-md text-sm ${testStatus === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                    {testMessage}
                </div>
            )}
            <div className="flex justify-center items-center space-x-4">
              <button
                className={`${buttonClasses.replace('block mx-auto', '')} disabled:bg-gray-400 disabled:cursor-not-allowed`}
                onClick={handleSave}
                disabled={!hasUnsavedChanges || saveStatus !== 'idle'}
              >
                {saveStatus === 'idle' && 'Save Settings'}
                {saveStatus === 'saving' && 'Saving...'}
                {saveStatus === 'saved' && (
                  <>
                    Saved <span role="img" aria-label="check mark">✅</span>
                  </>
                )}
              </button>
              <button className={`${buttonClasses.replace('block mx-auto', '')} disabled:bg-gray-400 disabled:cursor-not-allowed`} onClick={handleTestConnection} disabled={testStatus === 'testing' || hasUnsavedChanges}>
                  {testStatus === 'testing' ? 'Testing...' : 'Test Connection'}
              </button>
            </div>
            </div>
            <div className={settingsSectionClasses}>
              <h2 className="text-center mb-5 text-2xl font-bold">Inbox Vectorization</h2>
              <p className="text-center text-sm text-gray-600 mb-5">
                To enable semantic search over your emails, they need to be vectorized and stored. This process can take a few minutes.
              </p>
              <div className="flex justify-center items-center mb-5 space-x-3">
                <span>Inbox Vectorization Status: </span>
                <span className={getStatusClasses(inboxStatus)}>
                  {inboxStatus ? inboxStatus.charAt(0).toUpperCase() + inboxStatus.slice(1).replace('_', ' ') : 'Loading...'}
                </span>
                <button
                  className="py-1 px-3 text-xs rounded bg-amber-600 text-white cursor-pointer border-none"
                  onClick={handleRevectorize}
                  title="This will delete all existing email vector data and start from scratch. This action cannot be undone."
                >
                  Re-vectorize
                </button>
              </div>
              {embeddingConfigError && (
                <div className="text-center p-2 mb-4 rounded-md text-sm bg-red-100 text-red-800">
                    {embeddingConfigError}
                </div>
              )}
              <div className={settingRowClasses}>
                <label className={labelClasses} htmlFor="embedding-model">Embedding Model:</label>
                <div className="flex-1">
                  <select
                    id="embedding-model"
                    name="EMBEDDING_MODEL"
                    value={settings.EMBEDDING_MODEL || ''}
                    onChange={handleEmbeddingModelChange}
                    className={inputClasses}
                  >
                    {embeddingModels.map(model => (
                      <option key={model.model_name_from_key} value={model.model_name_from_key}>
                        {model.provider} - {model.model_name}
                      </option>
                    ))}
                  </select>
                  {selectedEmbeddingModel && !selectedEmbeddingModel.api_key_provided && (
                    <p className="text-red-500 text-xs mt-1">
                      Warning: API key for this model's provider ({selectedEmbeddingModel.provider}) is not configured.
                    </p>
                  )}
                </div>
              </div>
            </div>
            {version && <p className="text-center text-xs text-gray-400 mt-4">Version: {version}</p>}
          </div>
        </div>
        <div className={`transition-all duration-300 ease-in-out bg-white shadow-lg border-l overflow-y-auto ${isHelpPanelOpen ? 'w-full max-w-2xl' : 'w-0'}`}>
          {isHelpPanelOpen && <GoogleAppPasswordHelp onClose={() => setHelpPanelOpen(false)} />}
        </div>
      </div>
    </div>
  );
};

export default SettingsPage; 