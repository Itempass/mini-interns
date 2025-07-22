
import React, { useState } from 'react';
import ImapSettings from './ImapSettings';
import GoogleAppPasswordHelp from '../help/GoogleAppPasswordHelp';

interface ImapSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const ImapSettingsModal: React.FC<ImapSettingsModalProps> = ({ isOpen, onClose }) => {
  const [isHelpPanelOpen, setHelpPanelOpen] = useState(false);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-gray-900 bg-opacity-75 flex justify-center items-center">
        <div className={`bg-white rounded-lg shadow-2xl w-full h-[90vh] flex flex-col relative transition-all duration-300 ${isHelpPanelOpen ? 'max-w-7xl' : 'max-w-5xl'}`}>
            <div className="flex justify-between items-center p-4 border-b">
                <h2 className="text-xl font-bold">IMAP Connection Settings</h2>
                <button onClick={onClose} className="text-gray-500 hover:text-gray-800 text-3xl font-bold">&times;</button>
            </div>
            <div className="flex flex-row overflow-hidden flex-grow">
                <div className="flex-1 overflow-y-auto p-1">
                    <ImapSettings
                        showAdvancedSettings={false}
                        setHelpPanelOpen={setHelpPanelOpen}
                    />
                </div>
                {isHelpPanelOpen && (
                    <div className="w-1/2 border-l border-gray-200 overflow-y-auto">
                        <GoogleAppPasswordHelp onClose={() => setHelpPanelOpen(false)} />
                    </div>
                )}
            </div>
        </div>
    </div>
  );
};

export default ImapSettingsModal; 