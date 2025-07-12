'use client';

import React from 'react';

const NoWorkflowsView = () => {
  return (
    <div className="flex items-center justify-center h-full text-center">
      <div>
        <h2 className="text-2xl font-semibold">No Workflows</h2>
        <p className="mt-2 text-gray-500">
          Get started by creating a new workflow.
        </p>
      </div>
    </div>
  );
};

export default NoWorkflowsView; 