import { useState, useEffect } from 'react';

export function useTimezone() {
  const [timezone, setTimezone] = useState<string | null>(null);
  const [utcOffset, setUtcOffset] = useState<string | null>(null);

  useEffect(() => {
    // This code only runs in the browser after the component mounts
    
    // 1. Get the IANA timezone name
    const ianaTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    setTimezone(ianaTimezone);

    // 2. Calculate the current UTC offset for display
    const offsetInMinutes = new Date().getTimezoneOffset();
    const offsetInHours = -offsetInMinutes / 60;
    
    // Format it nicely, e.g., UTC+5 or UTC-4
    const offsetString = `UTC${offsetInHours >= 0 ? '+' : ''}${offsetInHours}`;
    setUtcOffset(offsetString);

  }, []); // Empty array means this runs once on app load

  return { timezone, utcOffset };
} 