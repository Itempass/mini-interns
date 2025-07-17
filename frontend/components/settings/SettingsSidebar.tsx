
import React from 'react';

interface SettingsSidebarProps {
  version: string;
}

const SettingsSidebar: React.FC<SettingsSidebarProps> = ({ version }) => {
  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold">Settings</h2>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        <ul>
          <li className="p-2 rounded-md cursor-pointer font-semibold border-2 border-black">
            IMAP Settings
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