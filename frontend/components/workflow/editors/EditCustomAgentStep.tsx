
import React, { useState, useEffect, useRef } from 'react';
import { CustomAgentStep, WorkflowStep, getAvailableLLMModels, LLMModel, getAvailableTools, Tool } from '../../../services/workflows_api';
import { Copy, AlertCircle, Calendar } from 'lucide-react';
import PlaceholderTextEditor from './PlaceholderTextEditor';
import NoReferencesHelp from '../../help/NoReferencesHelp';
import { useTimezone } from '../../../hooks/useTimezone';

interface EditCustomAgentStepProps {
  step: CustomAgentStep;
  onSave: (step: WorkflowStep) => void;
  onCancel: () => void;
  hasTrigger?: boolean;
  precedingSteps?: WorkflowStep[];
}

const EditCustomAgentStep: React.FC<EditCustomAgentStepProps> = ({ step, onSave, onCancel, hasTrigger = false, precedingSteps = [] }) => {
  const [currentStep, setCurrentStep] = useState(step);
  const [availableModels, setAvailableModels] = useState<LLMModel[]>([]);
  const [availableTools, setAvailableTools] = useState<Tool[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [initialPrompt, setInitialPrompt] = useState(step.system_prompt);
  const [isPromptDirty, setIsPromptDirty] = useState(false);
  const [showCopyMessage, setShowCopyMessage] = useState(false);
  const copyTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [showNoReferencesHelp, setShowNoReferencesHelp] = useState(false);
  const { timezone } = useTimezone();

  const hasNoReferences =
    (hasTrigger || (precedingSteps && precedingSteps.length > 0)) &&
    !currentStep.system_prompt.includes('<<trigger_output>>') &&
    !currentStep.system_prompt.includes('<<step_output.');

  const hasNoSelectedTools = !Object.values(currentStep.tools || {}).some(tool => tool.enabled);

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
        const newStep = { ...currentStep, model: models[0].id };
        setCurrentStep(newStep);
        onSave(newStep);
      }
      setIsLoading(false);
    };
    fetchData();
  }, []);

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const handleToolToggle = (toolId: string) => {
    const newTools = { ...(currentStep.tools || {}) };
    if (newTools[toolId]) {
      newTools[toolId].enabled = !newTools[toolId].enabled;
    } else {
      newTools[toolId] = { enabled: true };
    }
    const newStep = { ...currentStep, tools: newTools };
    setCurrentStep(newStep);
    onSave(newStep);
  };

  const handleModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newStep = { ...currentStep, model: e.target.value };
    setCurrentStep(newStep);
    onSave(newStep);
  };

  const handlePromptChange = (newValue: string) => {
    setCurrentStep({ ...currentStep, system_prompt: newValue });
    setIsPromptDirty(newValue !== initialPrompt);
  };
  
  const handlePromptSave = () => {
    onSave(currentStep);
    setInitialPrompt(currentStep.system_prompt);
    setIsPromptDirty(false);
  };

  const copyPlaceholder = async (placeholder: string) => {
    try {
      await navigator.clipboard.writeText(placeholder);
      setShowCopyMessage(true);
      
      // Clear any existing timeout
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
      
      // Set timeout to hide message after 3 seconds
      copyTimeoutRef.current = setTimeout(() => {
        setShowCopyMessage(false);
      }, 3000);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  };

  const copyDatePlaceholder = () => {
    if (timezone) {
      copyPlaceholder(`<<CURRENT_DATE.${timezone}>>`);
    } else {
      copyPlaceholder('<<CURRENT_DATE.UTC>>');
      console.warn("Timezone not yet available, falling back to UTC for placeholder.");
    }
  };

  return (
    <div className="p-6">
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700">System Prompt</label>
          {hasNoReferences && (
            <div className="mt-1">
              <span 
                className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-red-800 bg-red-100 rounded-full cursor-pointer hover:bg-red-200"
                onClick={() => setShowNoReferencesHelp(true)}
              >
                <AlertCircle size={12} />
                No references to previous outputs found!
              </span>
            </div>
          )}
          <div className="relative">
            <PlaceholderTextEditor
              value={currentStep.system_prompt}
              onChange={handlePromptChange}
              onSave={handlePromptSave}
              placeholder="e.g., You are an AI assistant that can search emails."
              className="mt-1"
              hasTrigger={hasTrigger}
              precedingSteps={precedingSteps}
              showSaveButton={isPromptDirty}
              rows={10}
            />
            
            {showCopyMessage && (
              <div className="absolute bottom-3 left-1/2 transform -translate-x-1/2 px-2 py-1 bg-white bg-opacity-40 backdrop-blur-sm text-gray-800 text-xs rounded border border-gray-300 border-opacity-40 shadow-sm">
                Copied! Paste inside your system prompt
              </div>
            )}
          </div>

          {/* Output Placeholders */}
          {(hasTrigger || precedingSteps.length > 0 || timezone) && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <p className="text-sm text-gray-600">Insert placeholders:</p>
              <button
                type="button"
                onClick={copyDatePlaceholder}
                className="px-3 py-1 bg-purple-100 text-purple-800 text-sm rounded-full hover:bg-purple-200 transition-colors flex items-center gap-1"
              >
                <Calendar size={12} />
                current date
              </button>
              {hasTrigger && (
                <button
                  type="button"
                  onClick={() => copyPlaceholder('<<trigger_output>>')}
                  className="px-3 py-1 bg-green-100 text-green-800 text-sm rounded-full hover:bg-green-200 transition-colors flex items-center gap-1"
                >
                  <Copy size={12} />
                  trigger output
                </button>
              )}
              {precedingSteps.map((precedingStep, index) => (
                <button
                  key={precedingStep.uuid}
                  type="button"
                  onClick={() => copyPlaceholder(`<<step_output.${precedingStep.uuid}>>`)}
                  className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full hover:bg-blue-200 transition-colors flex items-center gap-1"
                >
                  <Copy size={12} />
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
                disabled={isLoading}
            >
                {isLoading ? <option>Loading...</option> : availableModels.map(model => (
                    <option key={model.id} value={model.id}>{model.name}</option>
                ))}
            </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Tools</label>
          {hasNoSelectedTools && (
            <div className="mt-1">
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-red-800 bg-red-100 rounded-full"
              >
                <AlertCircle size={12} />
                This agent has no tools and cannot do anything.
              </span>
            </div>
          )}
          {isLoading ? <p className="text-sm text-gray-500">Loading tools...</p> : (
            <div className="mt-2 space-y-2 border rounded-md p-4 bg-white max-h-60 overflow-y-auto">
              {availableTools
                .sort((a, b) => {
                  const aSelected = currentStep.tools[a.id]?.enabled || false;
                  const bSelected = currentStep.tools[b.id]?.enabled || false;
                  if (aSelected && !bSelected) return -1;
                  if (!aSelected && bSelected) return 1;
                  return 0;
                })
                .map(tool => (
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
      </div>
      
      {/* Help Sidebar */}
      <div className={`fixed top-0 right-0 h-full transition-all duration-300 ease-in-out bg-white shadow-lg border-l overflow-y-auto z-20 ${showNoReferencesHelp ? 'w-full max-w-2xl' : 'w-0'}`}>
        {showNoReferencesHelp && <NoReferencesHelp onClose={() => setShowNoReferencesHelp(false)} />}
      </div>
    </div>
  );
};

export default EditCustomAgentStep; 