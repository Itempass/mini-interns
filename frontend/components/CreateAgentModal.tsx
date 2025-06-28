'use client';
import React, { useState, useRef } from 'react';
import { createAgent, importAgent, Agent } from '../services/api';

interface CreateAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAgentCreated: (newAgent: Agent) => void;
}

const CreateAgentModal: React.FC<CreateAgentModalProps> = ({ isOpen, onClose, onAgentCreated }) => {
  const [view, setView] = useState<'options' | 'scratch' | 'import'>('options');
  const [agentName, setAgentName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleCreateFromScratch = async () => {
    if (!agentName.trim()) {
      setError('Agent name is required.');
      return;
    }
    setError(null);
    setIsProcessing(true);
    try {
      const newAgent = await createAgent({ name: agentName, description: '' });
      onAgentCreated(newAgent);
      resetAndClose();
    } catch (err) {
      setError('Failed to create agent.');
      console.error(err);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setError(null);
      setIsProcessing(true);
      try {
        const newAgent = await importAgent(file);
        onAgentCreated(newAgent);
        resetAndClose();
      } catch (err: any) {
        setError(err.message || 'Failed to import agent.');
        console.error(err);
      } finally {
        setIsProcessing(false);
      }
    }
  };

  const resetAndClose = () => {
    setAgentName('');
    setError(null);
    setView('options');
    setIsProcessing(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-center z-50">
      <div className="bg-white rounded-lg p-8 w-full max-w-md">
        <h2 className="text-2xl font-bold mb-6 text-center">Create New Agent</h2>
        {error && <p className="text-red-500 text-sm mb-4 text-center">{error}</p>}
        {isProcessing && <p className="text-blue-500 text-sm mb-4 text-center">Processing...</p>}

        {view === 'options' && (
          <div className="flex justify-center space-x-4">
            <button
              onClick={() => setView('scratch')}
              className="px-6 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600"
            >
              Create from Scratch
            </button>
            <button
              onClick={() => setView('import')}
              className="px-6 py-2 bg-green-500 text-white rounded-md hover:bg-green-600"
            >
              Import from File
            </button>
          </div>
        )}

        {view === 'scratch' && !isProcessing && (
          <div>
            <input
              type="text"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              placeholder="Enter agent name"
              className="w-full p-2 border rounded-md mb-4"
              autoFocus
            />
            <div className="flex justify-end space-x-2">
              <button onClick={() => setView('options')} className="px-4 py-2 text-sm bg-gray-200 rounded-md">Back</button>
              <button onClick={handleCreateFromScratch} className="px-4 py-2 text-sm bg-blue-500 text-white rounded-md">Create</button>
            </div>
          </div>
        )}

        {view === 'import' && !isProcessing && (
          <div>
            <input
              type="file"
              accept=".json"
              onChange={handleFileChange}
              ref={fileInputRef}
              className="w-full p-2 border rounded-md mb-4"
            />
             <div className="flex justify-end space-x-2">
              <button onClick={() => setView('options')} className="px-4 py-2 text-sm bg-gray-200 rounded-md">Back</button>
            </div>
          </div>
        )}

        <button onClick={resetAndClose} className="absolute top-4 right-4 text-gray-500 hover:text-gray-800">&times;</button>
      </div>
    </div>
  );
};

export default CreateAgentModal; 