import React from 'react';

interface LogsSidebarProps {
  // Props will be added here when functionality is implemented
}

const LogsSidebar: React.FC<LogsSidebarProps> = ({}) => {
  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold">Log Filters</h2>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {/* Future filter options will go here */}
        <p className="text-sm text-gray-500">Filters are coming soon.</p>
      </div>
    </div>
  );
};

export default LogsSidebar; 