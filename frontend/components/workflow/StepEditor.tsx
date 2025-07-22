import React from 'react';
import { WorkflowStep, CustomLLMStep, CustomAgentStep, StopWorkflowCheckerStep } from '../../services/workflows_api';
import EditCustomLLMStep from './editors/EditCustomLLMStep';
import EditCustomAgentStep from './editors/EditCustomAgentStep';
import EditStopCheckerStep from './editors/EditStopCheckerStep';

interface StepEditorProps {
  step: WorkflowStep;
  workflowSteps: WorkflowStep[];
  onSave: (step: WorkflowStep) => void;
  hasTrigger?: boolean;
}

const StepEditor: React.FC<StepEditorProps> = ({ step, workflowSteps, onSave, hasTrigger = false }) => {
  // Find the current step's position in the workflow
  const currentStepIndex = workflowSteps.findIndex(s => s.uuid === step.uuid);
  const precedingSteps = workflowSteps.slice(0, currentStepIndex);

  switch (step.type) {
    case 'custom_llm':
      return (
        <EditCustomLLMStep 
          step={step as CustomLLMStep} 
          onSave={onSave} 
          onCancel={() => {}}
          hasTrigger={hasTrigger}
          precedingSteps={precedingSteps}
        />
      );
    case 'custom_agent':
      return (
        <EditCustomAgentStep 
          step={step as CustomAgentStep} 
          onSave={onSave} 
          onCancel={() => {}}
          hasTrigger={hasTrigger}
          precedingSteps={precedingSteps}
        />
      );
    case 'stop_checker': {
      return (
        <EditStopCheckerStep
          step={step as StopWorkflowCheckerStep}
          precedingSteps={precedingSteps}
          onSave={onSave}
          onCancel={() => {}}
        />
      );
    }
    default:
      return (
        <div className="p-4 border rounded-md bg-red-50 text-red-700">
          Error: Unsupported step type `{(step as any).type}`.
          <div className="mt-4">
            <button
                onClick={() => {}}
                className="px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300"
              >
                Close
            </button>
          </div>
        </div>
      );
  }
};

export default StepEditor; 