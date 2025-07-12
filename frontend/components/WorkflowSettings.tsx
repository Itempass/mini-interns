'use client';

import React, { useState, useEffect } from 'react';
import { Workflow, TriggerType, getAvailableTriggerTypes, setWorkflowTrigger, removeWorkflowTrigger } from '../services/workflows_api';

interface WorkflowSettingsProps {
  workflow: Workflow;
  onWorkflowUpdate: () => void;
}

const WorkflowSettings: React.FC<WorkflowSettingsProps> = ({ workflow, onWorkflowUpdate }) => {
  const [triggerTypes, setTriggerTypes] = useState<TriggerType[]>([]);
  const [selectedTriggerType, setSelectedTriggerType] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  useEffect(() => {
    const fetchTriggerTypes = async () => {
      const types = await getAvailableTriggerTypes();
      setTriggerTypes(types);
    };
    fetchTriggerTypes();
  }, []);

  const handleSetTrigger = async () => {
    if (!selectedTriggerType) return;
    
    setIsLoading(true);
    setSaveStatus('saving');
    
    try {
      const result = await setWorkflowTrigger(workflow.uuid, selectedTriggerType);
      if (result) {
        setSaveStatus('saved');
        onWorkflowUpdate();
        setTimeout(() => setSaveStatus('idle'), 2000);
      } else {
        setSaveStatus('error');
      }
    } catch (error) {
      console.error('Error setting trigger:', error);
      setSaveStatus('error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRemoveTrigger = async () => {
    if (!workflow.trigger_uuid) return;
    
    setIsLoading(true);
    setSaveStatus('saving');
    
    try {
      const result = await removeWorkflowTrigger(workflow.uuid);
      if (result) {
        setSaveStatus('saved');
        onWorkflowUpdate();
        setSelectedTriggerType('');
        setTimeout(() => setSaveStatus('idle'), 2000);
      } else {
        setSaveStatus('error');
      }
    } catch (error) {
      console.error('Error removing trigger:', error);
      setSaveStatus('error');
    } finally {
      setIsLoading(false);
    }
  };

  if (!workflow) {
    return <div>Select a workflow to see details.</div>;
  }

  const hasTrigger = Boolean(workflow.trigger_uuid);

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">{workflow.name}</h2>
      <p className="text-gray-600 mb-6">{workflow.description}</p>
      
      <div className="bg-white border rounded-lg p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Trigger Configuration</h3>
        
        {hasTrigger ? (
          <div className="space-y-4">
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-green-500 rounded-full"></div>
              <span className="text-green-700 font-medium">Trigger Active</span>
            </div>
            <p className="text-sm text-gray-600">
              This workflow has a trigger configured and will run automatically when the trigger conditions are met.
            </p>
            <button
              onClick={handleRemoveTrigger}
              disabled={isLoading}
              className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {isLoading ? 'Removing...' : 'Remove Trigger'}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-gray-400 rounded-full"></div>
              <span className="text-gray-600 font-medium">No Trigger Configured</span>
            </div>
            <p className="text-sm text-gray-600">
              Select a trigger type to automatically run this workflow when certain events occur.
            </p>
            
            <div className="flex items-end space-x-4">
              <div className="flex-1">
                <label htmlFor="trigger-select" className="block text-sm font-medium text-gray-700 mb-2">
                  Trigger Type
                </label>
                <select
                  id="trigger-select"
                  value={selectedTriggerType}
                  onChange={(e) => setSelectedTriggerType(e.target.value)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  disabled={isLoading}
                >
                  <option value="">Select a trigger type...</option>
                  {triggerTypes.map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.name}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleSetTrigger}
                disabled={!selectedTriggerType || isLoading}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                {isLoading ? 'Setting...' : 'Set Trigger'}
              </button>
            </div>
            
            {selectedTriggerType && (
              <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-md">
                {(() => {
                  const selectedType = triggerTypes.find(t => t.id === selectedTriggerType);
                  return selectedType ? (
                    <div>
                      <p className="text-sm font-medium text-blue-800">{selectedType.name}</p>
                      <p className="text-sm text-blue-600 mt-1">{selectedType.description}</p>
                      <p className="text-xs text-blue-500 mt-2">
                        <strong>Initial Data:</strong> {selectedType.initial_data_description}
                      </p>
                    </div>
                  ) : null;
                })()}
              </div>
            )}
          </div>
        )}
        
        {saveStatus === 'saved' && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-md">
            <p className="text-sm text-green-700">✓ Trigger configuration saved successfully!</p>
          </div>
        )}
        
        {saveStatus === 'error' && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md">
            <p className="text-sm text-red-700">✗ Failed to save trigger configuration. Please try again.</p>
          </div>
        )}
      </div>
      
      <div className="bg-white border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">Workflow Steps</h3>
        <p className="text-gray-600 text-sm">
          Workflow steps configuration will be available here in a future update.
        </p>
      </div>
    </div>
  );
};

export default WorkflowSettings; 