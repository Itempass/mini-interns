'use client';
import React, { useState, useEffect } from 'react';
import { getSettings, setSettings, AppSettings, getAgentSettings, setAgentSettings as apiSetAgentSettings } from '../services/api';

interface AgentSettings {
  systemPrompt: string;
  triggerConditions: string;
  userContext: string;
}

const HomePage = () => {
  const [settings, setSettingsState] = useState<AppSettings>({});
  const [agentSettings, setAgentSettings] = useState<AgentSettings>({
    systemPrompt: '',
    triggerConditions: '',
    userContext: '',
  });
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingField, setEditingField] = useState<keyof AgentSettings | null>(null);
  const [modalContent, setModalContent] = useState('');

  useEffect(() => {
    console.log('Component mounted. Fetching initial data.');
    const fetchSettings = async () => {
      const fetchedSettings = await getSettings();
      setSettingsState(fetchedSettings);
    };
    const fetchAgentSettings = async () => {
      const fetchedAgentSettings = await getAgentSettings();
      setAgentSettings({
        systemPrompt: fetchedAgentSettings.system_prompt || '',
        triggerConditions: fetchedAgentSettings.trigger_conditions || '',
        userContext: fetchedAgentSettings.user_context || '',
      });
    };
    fetchSettings();
    fetchAgentSettings();
  }, []);

  const handleSave = async () => {
    console.log('Save button clicked. Saving settings:', settings);
    await setSettings(settings);
    alert('Settings saved!');
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setSettingsState(prev => ({ ...prev, [name]: value }));
  };

  const handleEdit = (field: keyof AgentSettings) => {
    setEditingField(field);
    setModalContent(agentSettings[field]);
    setIsModalOpen(true);
  };

  const handleModalSave = async () => {
    if (editingField) {
      const newSettings = { ...agentSettings, [editingField]: modalContent };
      setAgentSettings(newSettings);
      await apiSetAgentSettings({
        system_prompt: newSettings.systemPrompt,
        trigger_conditions: newSettings.triggerConditions,
        user_context: newSettings.userContext,
      });
    }
    setIsModalOpen(false);
  };

  const handleModalClose = () => {
    setIsModalOpen(false);
  };

  const settingsSectionStyle: React.CSSProperties = {
    border: '1px solid #ccc',
    padding: '16px',
    marginBottom: '20px',
    borderRadius: '8px',
    backgroundColor: '#f9f9f9',
  };

  const settingRowStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    marginBottom: '12px',
  };

  const labelStyle: React.CSSProperties = {
    marginRight: '10px',
    width: '180px',
    textAlign: 'right',
    fontWeight: 'bold',
  };

  const inputStyle: React.CSSProperties = {
    flex: '1',
    padding: '8px',
    borderRadius: '4px',
    border: '1px solid #ccc',
  };

  const buttonStyle: React.CSSProperties = {
    padding: '10px 20px',
    border: 'none',
    borderRadius: '4px',
    backgroundColor: '#007bff',
    color: 'white',
    cursor: 'pointer',
    fontSize: '16px',
    display: 'block',
    margin: '0 auto',
  };

  const containerStyle: React.CSSProperties = {
    padding: '20px',
    maxWidth: '700px',
    margin: '0 auto',
    fontFamily: 'Arial, sans-serif',
  };

  const modalOverlayStyle: React.CSSProperties = {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1000,
  };

  const modalContentStyle: React.CSSProperties = {
    backgroundColor: 'white',
    padding: '20px',
    borderRadius: '8px',
    width: '800px',
    maxHeight: '80vh',
    display: 'flex',
    flexDirection: 'column',
    boxShadow: '0 4px 8px rgba(0,0,0,0.1)',
  };

  const modalTextAreaStyle: React.CSSProperties = {
    width: '100%',
    minHeight: '400px',
    marginBottom: '10px',
    padding: '8px',
    borderRadius: '4px',
    border: '1px solid #ccc',
    boxSizing: 'border-box',
    resize: 'vertical',
  };

  const modalButtonsStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'flex-end',
  };

  return (
    <div style={containerStyle}>
      <div style={settingsSectionStyle}>
        <h2 style={{ textAlign: 'center', marginBottom: '20px' }}>Settings</h2>
        <div style={settingRowStyle}>
          <label style={labelStyle} htmlFor="imap-server">IMAP Server:</label>
          <input style={inputStyle} type="text" id="imap-server" name="IMAP_SERVER" value={settings.IMAP_SERVER || ''} onChange={handleInputChange} />
        </div>
        <div style={settingRowStyle}>
          <label style={labelStyle} htmlFor="imap-user">IMAP User:</label>
          <input style={inputStyle} type="text" id="imap-user" name="IMAP_USERNAME" value={settings.IMAP_USERNAME || ''} onChange={handleInputChange} />
        </div>
        <div style={settingRowStyle}>
          <label style={labelStyle} htmlFor="imap-password">IMAP Password:</label>
          <input style={inputStyle} type="password" id="imap-password" name="IMAP_PASSWORD" value={settings.IMAP_PASSWORD || ''} onChange={handleInputChange} />
        </div>
        <div style={settingRowStyle}>
          <label style={labelStyle} htmlFor="openrouter-api-key">Openrouter API Key:</label>
          <input style={inputStyle} type="password" id="openrouter-api-key" name="OPENROUTER_API_KEY" value={settings.OPENROUTER_API_KEY || ''} onChange={handleInputChange} />
        </div>
        <div style={settingRowStyle}>
          <label style={labelStyle} htmlFor="openrouter-model">Openrouter Model:</label>
          <div style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
            <input
              style={inputStyle}
              type="text"
              id="openrouter-model"
              name="OPENROUTER_MODEL"
              value={settings.OPENROUTER_MODEL || ''}
              onChange={handleInputChange}
            />
            <span
              title="copy the exact model slug from openrouter's website"
              style={{ marginLeft: '10px', cursor: 'help', fontSize: '20px', color: '#666' }}
            >
              &#9432;
            </span>
          </div>
        </div>
        <button style={buttonStyle} onClick={handleSave}>Save Settings</button>
      </div>

      <div style={settingsSectionStyle}>
        <h2 style={{ textAlign: 'center', marginBottom: '20px' }}>Agent</h2>
        <p style={{ textAlign: 'center', marginTop: '-15px', marginBottom: '20px', color: '#666' }}>
          The agent will trigger each time a new email is received
        </p>
        
        <div style={settingRowStyle}>
          <label style={labelStyle}>System Prompt:</label>
          <div style={{ flex: '1' }}>
            <button style={{...buttonStyle, padding: '5px 10px', fontSize: '14px', margin: '0' }} onClick={() => handleEdit('systemPrompt')}>Edit</button>
          </div>
        </div>

        <div style={settingRowStyle}>
          <label style={labelStyle}>Trigger Conditions:</label>
          <div style={{ flex: '1' }}>
            <button style={{...buttonStyle, padding: '5px 10px', fontSize: '14px', margin: '0' }} onClick={() => handleEdit('triggerConditions')}>Edit</button>
          </div>
        </div>

        <div style={settingRowStyle}>
          <label style={labelStyle}>User Context:</label>
          <div style={{ flex: '1' }}>
            <button style={{...buttonStyle, padding: '5px 10px', fontSize: '14px', margin: '0' }} onClick={() => handleEdit('userContext')}>Edit</button>
          </div>
        </div>
      </div>

      <h1>Hello, Next.js!</h1>
      <p>This is a placeholder frontend using App Router.</p>
      
      {isModalOpen && (
        <div style={modalOverlayStyle}>
          <div style={modalContentStyle}>
            <h3 style={{marginTop: 0}}>Edit {editingField && (editingField.charAt(0).toUpperCase() + editingField.slice(1)).replace(/([A-Z])/g, ' $1').trim()}</h3>
            <textarea
              style={modalTextAreaStyle}
              value={modalContent}
              onChange={(e) => setModalContent(e.target.value)}
            />
            <div style={modalButtonsStyle}>
              <button style={{...buttonStyle, marginRight: '10px'}} onClick={handleModalSave}>Save</button>
              <button style={{...buttonStyle, backgroundColor: '#6c757d'}} onClick={handleModalClose}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default HomePage; 