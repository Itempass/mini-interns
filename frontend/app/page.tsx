'use client';
import React, { useState, useEffect } from 'react';
import { getSettings, setSettings, AppSettings } from '../services/api';

const HomePage = () => {
  const [settings, setSettingsState] = useState<AppSettings>({});

  useEffect(() => {
    console.log('Component mounted. Fetching initial data.');
    const fetchSettings = async () => {
      const fetchedSettings = await getSettings();
      setSettingsState(fetchedSettings);
    };
    fetchSettings();
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
      <h1>Hello, Next.js!</h1>
      <p>This is a placeholder frontend using App Router.</p>
    </div>
  );
};

export default HomePage; 