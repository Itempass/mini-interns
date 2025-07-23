import { cache } from 'react';

export const getAuthMode = cache(async (): Promise<'auth0' | 'password' | 'none'> => {
  const apiUrl = process.env.NEXT_PUBLIC_API_BASE_URL || `http://127.0.0.1:${process.env.CONTAINERPORT_API}`;
  const modeUrl = `${apiUrl}/auth/mode`;

  try {
    const res = await fetch(modeUrl, {
      // Use 'no-store' to ensure we always get the latest mode from the backend.
      // This is important because the backend's configuration is the single source of truth.
      cache: 'no-store',
    });
    
    if (!res.ok) {
      console.error('Failed to fetch auth mode:', res.status, res.statusText);
      // Fail-safe: If we can't determine the mode, assume 'none' to avoid locking users out.
      // The protected backend API will still prevent unauthorized access.
      return 'none';
    }
    
    const data = await res.json();
    return data.mode;
  } catch (error) {
    console.error('Error fetching auth mode:', error);
    return 'none';
  }
}); 