
import React, { useState, useEffect } from 'react';
import { CustomAgentStep, WorkflowStep, getAvailableLLMModels, LLMModel, getAvailableTools, Tool } from '../../../services/workflows_api';

interface EditCustomAgentStepProps {
  step: CustomAgentStep;
  onSave: (step: WorkflowStep) => void;
  onCancel: () => void;
}

const EditCustomAgentStep: React.FC<EditCustomAgentStepProps> = ({ step, onSave, onCancel }) => {
  const [currentStep, setCurrentStep] = useState(step);
  const [availableModels, setAvailableModels] = useState<LLMModel[]>([]);
  const [availableTools, setAvailableTools] = useState<Tool[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      const [models, tools] = await Promise.all([
        getAvailableLLMModels(),
        getAvailableTools()
      ]);
      setAvailableModels(models);
      setAvailableTools(tools);
      
      if (!currentStep.model && models.length > 0) {
        setCurrentStep(prev => ({ ...prev, model: models[0].id }));
      }
      setIsLoading(false);
    };
    fetchData();
  }, []);

  const handleToolToggle = (toolId: string) => {
    setCurrentStep(prev => {
      const newTools = { ...prev.tools };
      if (newTools[toolId]) {
        newTools[toolId].enabled = !newTools[toolId].enabled;
      } else {
        newTools[toolId] = { enabled: true };
      }
      return { ...prev, tools: newTools };
    });
  };

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
                disabled={isLoading}
            >
                {isLoading ? <option>Loading...</option> : availableModels.map(model => (
                    <option key={model.id} value={model.id}>{model.name}</option>
                ))}
            </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Tools</label>
          {isLoading ? <p className="text-sm text-gray-500">Loading tools...</p> : (
            <div className="mt-2 space-y-2 border rounded-md p-4 bg-white max-h-60 overflow-y-auto">
              {availableTools.map(tool => (
                <div key={tool.id} className="flex items-center">
                  <input
                    id={`tool-${tool.id}`}
                    type="checkbox"
                    checked={currentStep.tools[tool.id]?.enabled || false}
                    onChange={() => handleToolToggle(tool.id)}
                    className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <label htmlFor={`tool-${tool.id}`} className="ml-3 text-sm text-gray-700">
                    <span className="font-medium">{tool.name}</span>
                    <span className="text-gray-500 ml-2">({tool.server})</span>
                    <p className="text-xs text-gray-500">{tool.description}</p>
                  </label>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <label htmlFor="step-system-prompt" className="block text-sm font-medium text-gray-700">System Prompt</label>
          <textarea
            id="step-system-prompt"
            value={currentStep.system_prompt}
            onChange={(e) => setCurrentStep({ ...currentStep, system_prompt: e.target.value })}
            rows={10}
            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            placeholder="e.g., You are an AI assistant that can search emails."
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

export default EditCustomAgentStep; 