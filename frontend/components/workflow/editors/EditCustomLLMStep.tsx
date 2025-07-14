
import React, { useState, useEffect } from 'react';
import { CustomLLMStep, WorkflowStep, getAvailableLLMModels, LLMModel } from '../../../services/workflows_api';

interface EditCustomLLMStepProps {
  step: CustomLLMStep;
  onSave: (step: WorkflowStep) => void;
  onCancel: () => void;
}

const EditCustomLLMStep: React.FC<EditCustomLLMStepProps> = ({ step, onSave, onCancel }) => {
  const [currentStep, setCurrentStep] = useState(step);
  const [availableModels, setAvailableModels] = useState<LLMModel[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(true);

  useEffect(() => {
    const fetchModels = async () => {
      setIsLoadingModels(true);
      const models = await getAvailableLLMModels();
      setAvailableModels(models);
      // Ensure the step has a model selected if it doesn't already, defaulting to the first available.
      if (!currentStep.model && models.length > 0) {
        setCurrentStep(prev => ({ ...prev, model: models[0].id }));
      }
      setIsLoadingModels(false);
    };
    fetchModels();
  }, []); // Run only once on mount

  const handleSave = () => {
    onSave(currentStep);
  };

  return (
    <div className="p-4 border rounded-md bg-blue-50">
      <h4 className="font-semibold mb-4">Editing Step: {step.name}</h4>
      
      <div className="space-y-4">
        <div>
          <label htmlFor="step-name" className="block text-sm font-medium text-gray-700">Name</label>
          <input
            type="text"
            id="step-name"
            value={currentStep.name}
            onChange={(e) => setCurrentStep({ ...currentStep, name: e.target.value })}
            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        <div>
          <label htmlFor="step-description" className="block text-sm font-medium text-gray-700">Description</label>
          <textarea
            id="step-description"
            value={currentStep.description}
            onChange={(e) => setCurrentStep({ ...currentStep, description: e.target.value })}
            rows={3}
            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        <div>
            <label htmlFor="step-model" className="block text-sm font-medium text-gray-700">Language Model</label>
            <select
                id="step-model"
                value={currentStep.model}
                onChange={(e) => setCurrentStep({ ...currentStep, model: e.target.value })}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                disabled={isLoadingModels}
            >
                {isLoadingModels ? (
                    <option>Loading models...</option>
                ) : (
                    availableModels.map(model => (
                        <option key={model.id} value={model.id}>{model.name}</option>
                    ))
                )}
            </select>
        </div>

        <div>
          <label htmlFor="step-system-prompt" className="block text-sm font-medium text-gray-700">System Prompt</label>
          <textarea
            id="step-system-prompt"
            value={currentStep.system_prompt}
            onChange={(e) => setCurrentStep({ ...currentStep, system_prompt: e.target.value })}
            rows={10}
            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            placeholder="e.g., You are a helpful assistant."
          />
        </div>
      </div>

      <div className="flex justify-end space-x-2 mt-6">
        <button
          onClick={onCancel}
          className="px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          Save
        </button>
      </div>
    </div>
  );
};

export default EditCustomLLMStep; 