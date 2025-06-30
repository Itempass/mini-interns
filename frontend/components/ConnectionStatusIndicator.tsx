'use client';

import React, { useState, useEffect } from 'react';
import { testImapConnection } from '../services/api';

const ConnectionStatusIndicator = () => {
  const [isConnected, setIsConnected] = useState<boolean | null>(null);

  useEffect(() => {
    const checkConnection = async () => {
      try {
        await testImapConnection();
        setIsConnected(true);
      } catch (error) {
        setIsConnected(false);
      }
    };

    checkConnection();
    const intervalId = setInterval(checkConnection, 30000); 

    return () => clearInterval(intervalId);
  }, []);

  if (isConnected === null) {
    return (
      <div className="p-4 border-t border-gray-200 text-sm text-gray-500 flex items-center">
        <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-gray-400 mr-2"></div>
        Checking connection...
      </div>
    );
  }

  return (
    <div className="p-4 border-t border-gray-200 text-sm flex items-center">
      {isConnected ? (
        <>
          <div className="w-3 h-3 rounded-full bg-green-500 mr-2"></div>
          <span className="text-gray-700 font-medium">IMAP connected</span>
        </>
      ) : (
        <>
          <div className="w-3 h-3 rounded-full bg-red-500 mr-2"></div>
          <span className="text-gray-700 font-medium">IMAP not connected</span>
        </>
      )}
    </div>
  );
};

export default ConnectionStatusIndicator; 