'use client';

import React from 'react';
import Link from 'next/link';

const NoAgentsView = () => {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center p-8 bg-gray-100">
      <div className="max-w-lg">
        <h2 className="text-2xl font-semibold text-gray-900 mb-2">Welcome!</h2>
        <p className="text-gray-600 mb-6">
          To get started, you need to connect your email inbox.
        </p>
        <div className="text-left text-gray-700 bg-white p-6 rounded-lg shadow-md border border-gray-200">
          <h3 className="text-lg font-semibold text-gray-800 mb-3">How to begin:</h3>
          <ol className="list-decimal list-inside space-y-3">
            <li>
              Navigate to the{' '}
              <Link href="/settings" className="text-blue-600 hover:underline font-medium">
                Settings
              </Link>{' '}
              page to connect your inbox. You can find it in the top bar.
            </li>
            <li>Once your inbox is connected, you can create your first agent using the button in the sidebar.</li>
          </ol>
        </div>
      </div>
    </div>
  );
};

export default NoAgentsView; 