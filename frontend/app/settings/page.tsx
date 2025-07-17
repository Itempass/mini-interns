'use client';
import React, { useState, useEffect } from 'react';
import { getSettings, setSettings, AppSettings, EmbeddingModel, initializeInbox, getInboxInitializationStatus, testImapConnection, reinitializeInbox, getVersion, getToneOfVoiceProfile, rerunToneAnalysis, getToneOfVoiceStatus } from '../../services/api';
import TopBar from '../../components/TopBar';

import GoogleAppPasswordHelp from '../../components/help/GoogleAppPasswordHelp';
import SettingsSidebar from '../../components/settings/SettingsSidebar';
import ImapSettings from '../../components/settings/ImapSettings';
import McpServersSettings from '../../components/settings/McpServersSettings';

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
  const [toneOfVoiceProfile, setToneOfVoiceProfile] = useState<any>(null);
  const [toneAnalysisStatus, setToneAnalysisStatus] = useState<string | null>(null);
  const [toneAnalysisMessage, setToneAnalysisMessage] = useState<string>('');
  const [showGmailWarning, setShowGmailWarning] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('imap');

  const hasUnsavedChanges = JSON.stringify(settings) !== JSON.stringify(initialSettings);

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

      if (fetchedSettings.IMAP_SERVER && fetchedSettings.IMAP_SERVER.toLowerCase().trim() !== 'imap.gmail.com') {
        setShowGmailWarning(true);
      } else {
        setShowGmailWarning(false);
      }

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
    const fetchToneProfile = async () => {
      try {
        const profile = await getToneOfVoiceProfile();
        setToneOfVoiceProfile(profile);
      } catch (error) {
        console.error("Failed to fetch tone of voice profile:", error);
      }
    };

    fetchSettings();
    fetchVersion();
    fetchToneProfile();
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
      await fetchStatus();
    }, 3000); // Poll every 3 seconds

    return () => clearInterval(interval); // Cleanup on unmount
  }, []);

  useEffect(() => {
    const fetchToneStatus = async () => {
        const status = await getToneOfVoiceStatus();
        setToneAnalysisStatus(status);
    };

    fetchToneStatus(); // Initial fetch

    const interval = setInterval(async () => {
        await fetchToneStatus();
    }, 3000); // Poll every 3 seconds

    return () => clearInterval(interval); // Cleanup on unmount
  }, []);

  // Effect to re-fetch the tone profile only when the analysis completes.
  useEffect(() => {
    if (toneAnalysisStatus === 'completed') {
        const fetchToneProfile = async () => {
            const profile = await getToneOfVoiceProfile();
            setToneOfVoiceProfile(profile);
        };
        fetchToneProfile();
    }
  }, [toneAnalysisStatus]);

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

  const handleImapServerBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    const value = e.target.value;
    if (value && value.toLowerCase().trim() !== 'imap.gmail.com') {
        setShowGmailWarning(true);
    } else {
        setShowGmailWarning(false);
    }
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
      // Manually trigger a status fetch to update UI immediately
      const status = await getInboxInitializationStatus();
      setInboxStatus(status);
      const toneStatus = await getToneOfVoiceStatus();
      setToneAnalysisStatus(toneStatus);
    }
  };

  const handleRerunToneAnalysis = async () => {
    setToneAnalysisMessage('');
    try {
        await rerunToneAnalysis();
        // The polling will take care of updating the status
    } catch (error: any) {
        setToneAnalysisMessage(error.message || 'An unknown error occurred.');
        setToneAnalysisStatus('failed'); // Manually set to failed on client-side error
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
  
  return (
    <div className="flex flex-col h-screen relative" style={{
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
                    settings={settings}
                    initialSettings={initialSettings}
                    embeddingModels={embeddingModels}
                    inboxStatus={inboxStatus}
                    testStatus={testStatus}
                    testMessage={testMessage}
                    saveStatus={saveStatus}
                    setHelpPanelOpen={setHelpPanelOpen}
                    showEmbeddingModelSaved={showEmbeddingModelSaved}
                    embeddingConfigError={embeddingConfigError}
                    toneOfVoiceProfile={toneOfVoiceProfile}
                    toneAnalysisStatus={toneAnalysisStatus}
                    toneAnalysisMessage={toneAnalysisMessage}
                    showGmailWarning={showGmailWarning}
                    hasUnsavedChanges={hasUnsavedChanges}
                    handleSave={handleSave}
                    handleInputChange={handleInputChange}
                    handleImapServerBlur={handleImapServerBlur}
                    handleEmbeddingModelChange={handleEmbeddingModelChange}
                    handleTestConnection={handleTestConnection}
                    handleRevectorize={handleRevectorize}
                    handleRerunToneAnalysis={handleRerunToneAnalysis}
                    getStatusClasses={getStatusClasses}
                    setSettingsState={setSettingsState}
                />
            )}
            {selectedCategory === 'mcp' && <McpServersSettings />}
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