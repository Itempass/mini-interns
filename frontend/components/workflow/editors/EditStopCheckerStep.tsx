
import React, { useState } from 'react';
import { StopWorkflowCheckerStep, WorkflowStep } from '../../../services/workflows_api';

interface EditStopCheckerStepProps {
  step: StopWorkflowCheckerStep;
  precedingSteps: WorkflowStep[];
  onSave: (step: WorkflowStep) => void;
  onCancel: () => void;
}

const EditStopCheckerStep: React.FC<EditStopCheckerStepProps> = ({ step, precedingSteps, onSave, onCancel }) => {
  const [currentStep, setCurrentStep] = useState(step);
  const [matchValuesText, setMatchValuesText] = useState(step.match_values.join('\n'));

  const handleSave = () => {
    const newMatchValues = matchValuesText.split('\n').map(s => s.trim()).filter(Boolean);
    onSave({ ...currentStep, match_values: newMatchValues });
  };
  
  const handleStepToCheckChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newUuid = e.target.value;
    setCurrentStep({ ...currentStep, step_to_check_uuid: newUuid === 'null' ? null : newUuid });
  };


  return (
    <div className="p-4 border rounded-md bg-gray-50">
      <h4 className="font-semibold mb-4 text-gray-800">Editing Step: {step.name}</h4>
      
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
            rows={2}
            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        <div className="p-4 border rounded-md bg-white space-y-3">
            <div>
                <label className="text-sm font-medium text-gray-700">Step to Check</label>
                <p className="text-xs text-gray-500 mb-1">Select the previous step whose output you want to evaluate.</p>
                <select
                    value={currentStep.step_to_check_uuid ?? 'null'}
                    onChange={handleStepToCheckChange}
                    className="mt-1 block w-full text-sm px-3 py-2 border border-gray-300 rounded-md"
                    disabled={precedingSteps.length === 0}
                >
                    <option value="null" disabled={currentStep.step_to_check_uuid !== null}>-- Select a Step --</option>
                    {precedingSteps.map(pStep => (
                        <option key={pStep.uuid} value={pStep.uuid}>{pStep.name} ({pStep.type})</option>
                    ))}
                </select>
                {precedingSteps.length === 0 && <p className="text-xs text-red-500 mt-1">No previous steps available to check.</p>}
            </div>

            <div>
                <label className="text-sm font-medium text-gray-700">Condition</label>
                 <p className="text-xs text-gray-500 mb-1">Decide whether to stop or continue the workflow based on the output.</p>
                <select
                    value={currentStep.check_mode}
                    onChange={(e) => setCurrentStep({ ...currentStep, check_mode: e.target.value as StopWorkflowCheckerStep['check_mode'] })}
                    className="mt-1 block w-full text-sm px-3 py-2 border border-gray-300 rounded-md"
                >
                    <option value="stop_if_output_contains">Stop workflow if output contains...</option>
                    <option value="continue_if_output_contains">Continue workflow if output contains...</option>
                </select>
            </div>

             <div>
                <label className="text-sm font-medium text-gray-700">
                    {currentStep.check_mode === 'stop_if_output_contains' ? 'Values that will STOP the workflow' : 'Values that will ALLOW the workflow to continue'}
                </label>
                <p className="text-xs text-gray-500 mb-1">Enter one value per line. The check is case-insensitive. The workflow will stop if ANY of these values are found in the step's output.</p>
                <textarea
                    value={matchValuesText}
                    onChange={(e) => setMatchValuesText(e.target.value)}
                    rows={4}
                    className="mt-1 block w-full text-sm px-3 py-2 border border-gray-300 rounded-md font-mono"
                    placeholder="e.g.&#10;Approved&#10;Success&#10;Complete"
                />
            </div>
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

export default EditStopCheckerStep; 