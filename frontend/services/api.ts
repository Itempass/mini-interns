const API_URL = 'http://localhost:5001'; // The backend is on port 5001

export interface AppSettings {
  IMAP_SERVER?: string;
  IMAP_USERNAME?: string;
  IMAP_PASSWORD?: string;
  OPENROUTER_API_KEY?: string;
  OPENROUTER_MODEL?: string;
}

export const getSettings = async (): Promise<AppSettings> => {
  console.log('Fetching settings...');
  try {
    const response = await fetch(`${API_URL}/settings`);
    if (!response.ok) {
      console.error('Failed to fetch settings. Status:', response.status);
      throw new Error('Failed to fetch settings');
    }
    const data = await response.json();
    console.log('Successfully fetched settings:', data);
    return data;
  } catch (error) {
    console.error('An error occurred while fetching settings:', error);
    return {};
  }
};

export const setSettings = async (settings: AppSettings) => {
  console.log('Setting settings:', settings);
  try {
    const response = await fetch(`${API_URL}/settings`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(settings),
    });
    if (!response.ok) {
      console.error('Failed to set settings. Status:', response.status);
      throw new Error('Failed to set settings');
    }
    const result = await response.json();
    console.log('Successfully set settings:', result);
    return result;
  } catch (error) {
    console.error('An error occurred while setting settings:', error);
    return null;
  }
};

export const getOpenRouterModel = async () => {
  const settings = await getSettings();
  return settings.OPENROUTER_MODEL || '';
};

export const setOpenRouterModel = async (model: string) => {
  return await setSettings({ OPENROUTER_MODEL: model });
}; 