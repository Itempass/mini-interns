
import React from 'react';

interface SettingsSidebarProps {
  version: string;
  selectedCategory: string;
  setSelectedCategory: (category: string) => void;
}

const SettingsSidebar: React.FC<SettingsSidebarProps> = ({ version, selectedCategory, setSelectedCategory }) => {
  const getListItemClasses = (category: string) => {
    const baseClasses = "p-2 rounded-md cursor-pointer font-semibold";
    if (selectedCategory === category) {
      return `${baseClasses} border-2 border-black`;
    }
    return `${baseClasses} hover:bg-gray-100`;
  };

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex justify-between items-center p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold">Settings</h2>
      </div>
      <div className="flex-1 overflow-y-auto p-4 min-h-0">
        <ul className="space-y-2">
          <li
            className={getListItemClasses('balance')}
            onClick={() => setSelectedCategory('balance')}
          >
            Balance
          </li>
          <li
            className={getListItemClasses('usage_history')}
            onClick={() => setSelectedCategory('usage_history')}
          >
            Usage History
          </li>
          <li
            className={getListItemClasses('imap')}
            onClick={() => setSelectedCategory('imap')}
          >
            IMAP Settings
          </li>
          <li
            className={getListItemClasses('mcp')}
            onClick={() => setSelectedCategory('mcp')}
          >
            MCP Servers
          </li>
        </ul>
      </div>
      {version && (
        <div className="p-4 text-center text-xs text-gray-500 border-t border-gray-200">
          v{version}
        </div>
      )}
    </div>
  );
};

export default SettingsSidebar; 