
import React, { useState, useEffect } from 'react';
import { Copy, HelpCircle } from 'lucide-react';
import { 
    AppSettings, 
    EmbeddingModel, 
    getSettings, 
    setSettings, 
    getInboxInitializationStatus, 
    testImapConnection, 
    reinitializeInbox, 
    getToneOfVoiceProfile, 
    rerunToneAnalysis, 
    getToneOfVoiceStatus,
    initializeInbox
} from '../../services/api';
import ExpandableProfile from '../ExpandableProfile';

interface ImapSettingsProps {
    showAdvancedSettings?: boolean;
    setHelpPanelOpen: (isOpen: boolean) => void;
}

const ImapSettings: React.FC<ImapSettingsProps> = ({ 
    showAdvancedSettings = true,
    setHelpPanelOpen,
 }) => {
    const [settings, setSettingsState] = useState<AppSettings>({});
    const [initialSettings, setInitialSettings] = useState<AppSettings>({});
    const [embeddingModels, setEmbeddingModels] = useState<EmbeddingModel[]>([]);
    const [inboxStatus, setInboxStatus] = useState<string | null>(null);
    const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle');
    const [testMessage, setTestMessage] = useState<string>('');
    const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
    const [embeddingConfigError, setEmbeddingConfigError] = useState<string>('');
    const [toneOfVoiceProfile, setToneOfVoiceProfile] = useState<any>(null);
    const [toneAnalysisStatus, setToneAnalysisStatus] = useState<string | null>(null);
    const [toneAnalysisMessage, setToneAnalysisMessage] = useState<string>('');
    const [showGmailWarning, setShowGmailWarning] = useState(false);

    const hasUnsavedChanges = JSON.stringify(settings) !== JSON.stringify(initialSettings);

    const attemptAutoVectorization = async (currentSettings: AppSettings) => {
        if (currentSettings.IMAP_SERVER && currentSettings.IMAP_USERNAME && currentSettings.IMAP_PASSWORD) {
          try {
            await testImapConnection();
            const status = await getInboxInitializationStatus();
            if (status === 'not_started' || status === 'failed') {
              await initializeInbox();
            }
          } catch (error) {
            console.error("Automatic vectorization check failed.", error);
          }
        }
    };

    useEffect(() => {
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
            const selectedModel = fetchedModels.find(m => m.model_name_from_key === fetchedSettings.EMBEDDING_MODEL);
            if (selectedModel && !selectedModel.api_key_provided) {
              setEmbeddingConfigError(`API key for ${selectedModel.provider} is not configured.`);
            } else {
              setEmbeddingConfigError('');
            }
          }
    
          await attemptAutoVectorization(fetchedSettings);
        };
        const fetchToneProfile = async () => {
          try {
            const profile = await getToneOfVoiceProfile();
            setToneOfVoiceProfile(profile);
          } catch (error) {
            console.error("Failed to fetch tone of voice profile:", error);
          }
        };
    
        fetchSettings();
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
        if (!showAdvancedSettings) return;
        const fetchStatus = async () => {
          const status = await getInboxInitializationStatus();
          setInboxStatus(status);
        };
        fetchStatus();
        const interval = setInterval(fetchStatus, 3000);
        return () => clearInterval(interval);
      }, [showAdvancedSettings]);
    
      useEffect(() => {
        if (!showAdvancedSettings) return;
        const fetchToneStatus = async () => {
            const status = await getToneOfVoiceStatus();
            setToneAnalysisStatus(status);
        };
        fetchToneStatus();
        const interval = setInterval(fetchToneStatus, 3000);
        return () => clearInterval(interval);
      }, [showAdvancedSettings]);
    
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
        setSettingsState(prev => ({ ...prev, EMBEDDING_MODEL: newModelKey }));
    
        const selectedModel = embeddingModels.find(m => m.model_name_from_key === newModelKey);
        if (!selectedModel || !selectedModel.api_key_provided) {
            return;
        }
    
        if (newModelKey === initialSettings.EMBEDDING_MODEL) {
            setEmbeddingConfigError('');
            return;
        }
    
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
                setSettingsState(initialSettings);
            }
        } else {
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
          setInboxStatus(await getInboxInitializationStatus());
          setToneAnalysisStatus(await getToneOfVoiceStatus());
        }
      };
    
      const handleRerunToneAnalysis = async () => {
        setToneAnalysisMessage('');
        try {
            await rerunToneAnalysis();
        } catch (error: any) {
            setToneAnalysisMessage(error.message || 'An unknown error occurred.');
            setToneAnalysisStatus('failed');
        }
      };

    const getStatusClasses = (status: string | null): string => {
        switch (status) {
          case 'completed': return 'bg-green-100 text-green-800 px-2 py-1 rounded-full text-sm';
          case 'running': return 'bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-sm animate-pulse';
          case 'failed': return 'bg-red-100 text-red-800 px-2 py-1 rounded-full text-sm';
          default: return 'bg-gray-100 text-gray-800 px-2 py-1 rounded-full text-sm';
        }
    };

    const handleCopy = (text: string) => {
        navigator.clipboard.writeText(text).then(() => {}, (err) => {
          console.error('Failed to copy text: ', err);
        });
      };
    
    const copyButtonStyle = "bg-gray-100 border border-gray-300 rounded-full w-6 h-6 flex items-center justify-center cursor-pointer ml-2";
    const settingsSectionClasses = "border border-gray-300 p-4 mb-5 rounded-lg bg-gray-50";
    const settingRowClasses = "flex items-center mb-3";
    const labelClasses = "mr-2 w-48 text-right font-bold";
    const inputClasses = "w-full p-2 rounded border border-gray-300 box-border";
    const buttonClasses = "py-2 px-5 border-none rounded bg-blue-500 text-white cursor-pointer text-base block mx-auto";

    const selectedEmbeddingModel = embeddingModels.find(m => m.model_name_from_key === settings.EMBEDDING_MODEL);

  return (
    <div className="">
        <div className="p-10 max-w-4xl mx-auto font-sans">
        <div className={settingsSectionClasses}>
            <h2 className="text-center mb-5 text-2xl font-bold">Connection Settings</h2>
            <p className="text-center text-sm text-gray-600 mb-5">
            All settings are saved locally to your Docker Container. Your IMAP password is encrypted.
            </p>
            
            {showGmailWarning && (
            <div className="text-center p-2 mb-4 rounded-md text-sm bg-orange-100 text-orange-800 border border-orange-200">
                ⚠️ Only gmail supported for now! Get in touch with us if you're using Outlook.
            </div>
            )}
            
            <div className={settingRowClasses}>
            <label className={labelClasses}>IMAP Server:</label>
            <div className="flex-1">
            <input className={inputClasses} type="text" id="imap-server" name="IMAP_SERVER" value={settings.IMAP_SERVER || ''} onChange={handleInputChange} onBlur={handleImapServerBlur} />
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
                <button onClick={() => setHelpPanelOpen(true)} className="flex items-center text-xs text-blue-500 hover:underline">
                <HelpCircle size={14} className="mr-1" />
                Where to find your gmail App Password
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
        {showAdvancedSettings && (
            <>
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
                <div className={settingsSectionClasses}>
                    <h2 className="text-center mb-5 text-2xl font-bold">Tone of Voice</h2>
                    <p className="text-center text-sm text-gray-600 mb-5">
                        This is an auto-generated analysis of your writing style based on your emails.
                    </p>
                    <div className="flex justify-center items-center mb-5 space-x-3">
                        <span>Tone of Voice Status: </span>
                        <span className={getStatusClasses(toneAnalysisStatus)}>
                        {toneAnalysisStatus ? toneAnalysisStatus.charAt(0).toUpperCase() + toneAnalysisStatus.slice(1).replace('_', ' ') : 'Loading...'}
                        </span>
                        <button
                        className="py-1 px-3 text-xs rounded bg-amber-600 text-white cursor-pointer border-none disabled:bg-gray-400 disabled:cursor-not-allowed"
                        onClick={handleRerunToneAnalysis}
                        disabled={inboxStatus !== 'completed' || toneAnalysisStatus === 'running'}
                        title={inboxStatus !== 'completed' ? "Inbox vectorization must be complete before running analysis." : "Re-run the tone of voice analysis based on your latest emails."}
                        >
                        Re-run Analysis
                        </button>
                    </div>
                    <div className="bg-gray-100 p-4 rounded-md">
                        {toneOfVoiceProfile && Object.keys(toneOfVoiceProfile).length > 0 ? (
                        Object.entries(toneOfVoiceProfile).map(([lang, profile]) => (
                            <ExpandableProfile
                                key={lang}
                                language={lang}
                                profile={typeof profile === 'string' ? profile : JSON.stringify(profile)}
                            />
                        ))
                        ) : (
                        <p>No tone of voice profile found.</p>
                        )}
                    </div>
                    {toneAnalysisMessage && (
                        <div className={`text-center p-2 mt-4 rounded-md text-sm bg-red-100 text-red-800`}>
                            {toneAnalysisMessage}
                        </div>
                    )}
                </div>
            </>
        )}
        </div>
  </div>
  );
};

export default ImapSettings; 