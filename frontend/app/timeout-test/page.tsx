'use client';

import { useState } from 'react';

export default function TimeoutTestPage() {
  const [status, setStatus] = useState('Idle');
  const [delay, setDelay] = useState(65); // Default delay of 65 seconds

  const runTest = async () => {
    setStatus('Running...');
    try {
      const response = await fetch(`/api/proxy/timeout-test?delay=${delay}`);
      if (response.ok) {
        const data = await response.json();
        setStatus(`Success: ${JSON.stringify(data)}`);
      } else {
        setStatus(`Error: ${response.status} ${response.statusText}`);
      }
    } catch (error) {
      console.error('Timeout test error:', error);
      setStatus(`Failed: ${error.message}`);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100 dark:bg-gray-900">
      <h1 className="text-2xl font-bold mb-4">Timeout Test</h1>
      <div className="mb-4">
        <label htmlFor="delay" className="mr-2">Delay (seconds):</label>
        <input
          id="delay"
          type="number"
          value={delay}
          onChange={(e) => setDelay(Number(e.target.value))}
          className="p-2 border rounded"
        />
      </div>
      <button
        onClick={runTest}
        className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-700"
      >
        Run Test
      </button>
      <p className="mt-4">Status: {status}</p>
    </div>
  );
} 