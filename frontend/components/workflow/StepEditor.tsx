import React from 'react';
import { WorkflowStep, CustomLLMStep, CustomAgentStep, StopWorkflowCheckerStep } from '../../services/workflows_api';
import EditCustomLLMStep from './editors/EditCustomLLMStep';
import EditCustomAgentStep from './editors/EditCustomAgentStep';
import EditStopCheckerStep from './editors/EditStopCheckerStep';

interface StepEditorProps {
  step: WorkflowStep;
  workflowSteps: WorkflowStep[];
  onSave: (step: WorkflowStep) => void;
  onCancel: () => void;
}

const StepEditor: React.FC<StepEditorProps> = ({ step, workflowSteps, onSave, onCancel }) => {
  switch (step.type) {
    case 'custom_llm':
      return <EditCustomLLMStep step={step as CustomLLMStep} onSave={onSave} onCancel={onCancel} />;
    case 'custom_agent':
      return <EditCustomAgentStep step={step as CustomAgentStep} onSave={onSave} onCancel={onCancel} />;
    case 'stop_checker': {
      // The checker needs to know about previous steps to select one for its conditions.
      const precedingSteps = workflowSteps.slice(0, workflowSteps.findIndex(s => s.uuid === step.uuid));
      return (
        <EditStopCheckerStep
          step={step as StopWorkflowCheckerStep}
          precedingSteps={precedingSteps}
          onSave={onSave}
          onCancel={onCancel}
        />
      );
    }
    default:
      return (
        <div className="p-4 border rounded-md bg-red-50 text-red-700">
          Error: Unsupported step type `{(step as any).type}`.
          <div className="mt-4">
            <button
                onClick={onCancel}
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