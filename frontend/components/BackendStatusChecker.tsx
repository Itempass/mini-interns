'use client';
import React, { useState, useEffect } from 'react';
import { checkBackendHealth } from '../services/api';

const BackendStatusChecker = ({ children }: { children: React.ReactNode }) => {
  const [isBackendReady, setIsBackendReady] = useState(false);
  const [countdown, setCountdown] = useState(20);
  const [isTimedOut, setIsTimedOut] = useState(false);

  useEffect(() => {
    let intervalId: NodeJS.Timeout | null = null;

    const checkBackend = async () => {
      const isReady = await checkBackendHealth();
      if (isReady) {
        setIsBackendReady(true);
        if (intervalId) {
          clearInterval(intervalId);
        }
      }
    };

    // Initial check
    checkBackend();

    // Polling interval
    intervalId = setInterval(() => {
      checkBackend();
      setCountdown(prev => (prev > 0 ? prev - 1 : 0));
    }, 1000);

    // Timeout for showing the message
    const timeoutId = setTimeout(() => {
      setIsTimedOut(true);
    }, 20000);

    // Cleanup on component unmount
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
      clearTimeout(timeoutId);
    };
  }, []);

  if (isBackendReady) {
    return <>{children}</>;
  }

  return (
    <div className="fixed inset-0 bg-white bg-opacity-95 z-50 flex items-center justify-center">
      <div className="text-center">
        {isTimedOut ? (
          <div>
            <h2 className="text-2xl font-semibold text-gray-800 mb-4">
              Hmm, this is taking a while...
            </h2>
            <p className="text-gray-600">
              The backend is not responding. Please check your Docker logs for any issues.
            </p>
            <p className="text-gray-500 text-sm mt-2">
              (Still checking in the background)
            </p>
          </div>
        ) : (
          <div>
            <h2 className="text-2xl font-semibold text-gray-800 mb-4">
              Connecting to backend...
            </h2>
            <p className="text-gray-600">
              The application is starting up. This should only take a moment.
            </p>
            <p className="text-4xl font-bold text-gray-900 mt-4">
              {countdown}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default BackendStatusChecker; 