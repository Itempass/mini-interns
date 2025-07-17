'use client';

import React from 'react';
import { ArrowLeft } from 'lucide-react';

const NoWorkflowsView = () => {
  return (
    <div className="flex flex-col items-center justify-center h-full">
      <div className="relative text-center">
        <ArrowLeft
          className="absolute top-1/2 -left-16 -translate-y-1/2 text-gray-400"
          size={32}
          strokeWidth={1.5}
        />
        <div>
          <h2 className="text-2xl font-semibold">No workflows yet</h2>
          <p className="mt-2 text-gray-500">
            Get started by creating a new workflow.
          </p>
        </div>
      </div>
    </div>
  );
};

export default NoWorkflowsView; 