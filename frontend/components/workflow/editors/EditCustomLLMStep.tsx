
import React, { useState, useEffect, useRef } from 'react';
import { CustomLLMStep, WorkflowStep, getAvailableLLMModels, LLMModel } from '../../../services/workflows_api';

interface EditCustomLLMStepProps {
  step: CustomLLMStep;
  onSave: (step: WorkflowStep) => void;
  onCancel: () => void;
  hasTrigger?: boolean;
  precedingSteps?: WorkflowStep[];
}

const EditCustomLLMStep: React.FC<EditCustomLLMStepProps> = ({ step, onSave, onCancel, hasTrigger = false, precedingSteps = [] }) => {
  const [currentStep, setCurrentStep] = useState(step);
  const [availableModels, setAvailableModels] = useState<LLMModel[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [initialPrompt, setInitialPrompt] = useState(step.system_prompt);
  const [isPromptDirty, setIsPromptDirty] = useState(false);

  useEffect(() => {
    const fetchModels = async () => {
      setIsLoadingModels(true);
      const models = await getAvailableLLMModels();
      setAvailableModels(models);
      // Ensure the step has a model selected if it doesn't already, defaulting to the first available.
      if (!currentStep.model && models.length > 0) {
        const newStep = { ...currentStep, model: models[0].id };
        setCurrentStep(newStep);
        onSave(newStep);
      }
      setIsLoadingModels(false);
    };
    fetchModels();
  }, []); // Run only once on mount

  const handleModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newStep = { ...currentStep, model: e.target.value };
    setCurrentStep(newStep);
    onSave(newStep);
  };

  const handlePromptChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    setCurrentStep({ ...currentStep, system_prompt: newValue });
    setIsPromptDirty(newValue !== initialPrompt);
  };

  const handlePromptSave = () => {
    onSave(currentStep);
    setInitialPrompt(currentStep.system_prompt);
    setIsPromptDirty(false);
  };

  const insertPlaceholder = (placeholder: string) => {
    const textarea = textareaRef.current;
    if (textarea) {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const currentValue = currentStep.system_prompt;
      const newValue = currentValue.substring(0, start) + placeholder + currentValue.substring(end);
      
      const newStep = { ...currentStep, system_prompt: newValue };
      setCurrentStep(newStep);
      setIsPromptDirty(newValue !== initialPrompt);
      
      // Set cursor position after the inserted placeholder
      setTimeout(() => {
        textarea.focus();
        textarea.setSelectionRange(start + placeholder.length, start + placeholder.length);
      }, 0);
    }
  };

  return (
    <div className="p-6">
      <div className="space-y-4">
        <div>
          <label htmlFor="step-system-prompt" className="block text-sm font-medium text-gray-700">System Prompt</label>
          <div className="relative">
            <textarea
              ref={textareaRef}
              id="step-system-prompt"
              value={currentStep.system_prompt}
              onChange={handlePromptChange}
              rows={10}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
              placeholder="e.g., You are a helpful assistant."
            />
            
            {isPromptDirty && (
              <button
                onClick={handlePromptSave}
                className="absolute bottom-3 right-3 px-2 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700"
              >
                click to save
              </button>
            )}
          </div>

          {/* Output Placeholders */}
          {(hasTrigger || precedingSteps.length > 0) && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <p className="text-sm text-gray-600">Insert previous outputs into prompt:</p>
              {hasTrigger && (
                <button
                  type="button"
                  onClick={() => insertPlaceholder('<<trigger_output>>')}
                  className="px-3 py-1 bg-green-100 text-green-800 text-sm rounded-full hover:bg-green-200 transition-colors"
                >
                  trigger output
                </button>
              )}
              {precedingSteps.map((precedingStep, index) => (
                <button
                  key={precedingStep.uuid}
                  type="button"
                  onClick={() => insertPlaceholder(`<<step_output.${precedingStep.uuid}>>`)}
                  className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full hover:bg-blue-200 transition-colors"
                >
                  step {index + 2} output
                </button>
              ))}
            </div>
          )}
        </div>
        <div>
            <label htmlFor="step-model" className="block text-sm font-medium text-gray-700">Language Model</label>
            <select
                id="step-model"
                value={currentStep.model}
                onChange={handleModelChange}
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
      </div>
    </div>
  );
};

export default EditCustomLLMStep; 