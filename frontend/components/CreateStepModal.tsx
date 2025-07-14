'use client';

import React, { useState, useEffect } from 'react';
import { StepType, getAvailableStepTypes, addWorkflowStep, WorkflowWithDetails } from '../services/workflows_api';

interface CreateStepModalProps {
  workflowId: string;
  isOpen: boolean;
  onClose: () => void;
  onStepCreated: (updatedWorkflow: WorkflowWithDetails) => void;
}

const CreateStepModal: React.FC<CreateStepModalProps> = ({ workflowId, isOpen, onClose, onStepCreated }) => {
  const [stepTypes, setStepTypes] = useState<StepType[]>([]);
  const [selectedStepType, setSelectedStepType] = useState<string>('');
  const [stepName, setStepName] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      const fetchStepTypes = async () => {
        setIsLoading(true);
        const types = await getAvailableStepTypes();
        setStepTypes(types);
        if (types.length > 0) {
          setSelectedStepType(types[0].type);
        }
        setIsLoading(false);
      };
      fetchStepTypes();
      setStepName('');
      setError(null);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedStepType || !stepName.trim()) {
      setError('Please select a step type and provide a name.');
      return;
    }

    setIsLoading(true);
    setError(null);

    const result = await addWorkflowStep(workflowId, selectedStepType, stepName);

    setIsLoading(false);

    if (result) {
      onStepCreated(result);
      onClose();
    } else {
      setError('Failed to create the step. Please try again.');
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center">
      <div className="bg-white rounded-lg p-8 shadow-xl w-full max-w-md">
        <h2 className="text-2xl font-bold mb-6">Add New Step</h2>
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label htmlFor="step-type-select" className="block text-sm font-medium text-gray-700 mb-2">
              Step Type
            </label>
            <select
              id="step-type-select"
              value={selectedStepType}
              onChange={(e) => setSelectedStepType(e.target.value)}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              disabled={isLoading || stepTypes.length === 0}
            >
              {stepTypes.length === 0 && <option>Loading types...</option>}
              {stepTypes.map((type) => (
                <option key={type.type} value={type.type}>
                  {type.name}
                </option>
              ))}
            </select>
          </div>
          <div className="mb-6">
            <label htmlFor="step-name-input" className="block text-sm font-medium text-gray-700 mb-2">
              Step Name
            </label>
            <input
              id="step-name-input"
              type="text"
              value={stepName}
              onChange={(e) => setStepName(e.target.value)}
              placeholder="e.g., 'Summarize Email'"
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              disabled={isLoading}
            />
          </div>
          {error && <p className="text-red-500 text-sm mb-4">{error}</p>}
          <div className="flex justify-end space-x-4">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300 disabled:bg-gray-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || !selectedStepType || !stepName.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400"
            >
              {isLoading ? 'Creating...' : 'Create Step'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CreateStepModal; 