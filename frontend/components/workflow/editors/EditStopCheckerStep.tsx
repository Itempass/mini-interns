
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
  const [initialMatchValues, setInitialMatchValues] = useState(step.match_values.join('\n'));

  const isDirty = matchValuesText !== initialMatchValues;

  const handleMatchValuesSave = () => {
    const newMatchValues = matchValuesText.split('\n').map(s => s.trim()).filter(Boolean);
    onSave({ ...currentStep, match_values: newMatchValues });
    setInitialMatchValues(matchValuesText);
  };
  
  const handleStepToCheckChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newUuid = e.target.value;
    const newStep = { ...currentStep, step_to_check_uuid: newUuid === 'null' ? null : newUuid };
    setCurrentStep(newStep);
    onSave(newStep);
  };

  const handleCheckModeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newCheckMode = e.target.value as StopWorkflowCheckerStep['check_mode'];
    const newStep = { ...currentStep, check_mode: newCheckMode };
    setCurrentStep(newStep);
    onSave(newStep);
  };

  return (
    <div className="p-6">
      <div className="space-y-4">
            <div>
                <label className="block text-sm font-medium text-gray-700">Step to Check</label>
                <p className="text-xs text-gray-500 mb-1">Select the previous step whose output you want to evaluate.</p>
                <select
                    value={currentStep.step_to_check_uuid ?? 'null'}
                    onChange={handleStepToCheckChange}
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
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
                <label className="block text-sm font-medium text-gray-700">Condition</label>
                 <p className="text-xs text-gray-500 mb-1">Decide whether to stop or continue the workflow based on the output.</p>
                <select
                    value={currentStep.check_mode}
                    onChange={handleCheckModeChange}
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                >
                    <option value="stop_if_output_contains">Stop workflow if output contains...</option>
                    <option value="continue_if_output_contains">Continue workflow if output contains...</option>
                </select>
            </div>

             <div>
                <label className="block text-sm font-medium text-gray-700">
                    {currentStep.check_mode === 'stop_if_output_contains' ? 'Values that will STOP the workflow' : 'Values that will ALLOW the workflow to continue'}
                </label>
                <p className="text-xs text-gray-500 mb-1">Enter one value per line. The check is case-insensitive. The workflow will stop if ANY of these values are found in the step's output.</p>
                <div className="relative">
                  <textarea
                      value={matchValuesText}
                      onChange={(e) => setMatchValuesText(e.target.value)}
                      rows={4}
                      className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md font-mono shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                      placeholder="e.g.&#10;Approved&#10;Success&#10;Complete"
                  />
                  {isDirty && (
                    <button
                      onClick={handleMatchValuesSave}
                      className="absolute bottom-2 right-2 px-3 py-1 bg-blue-600 text-white text-xs font-semibold rounded-md hover:bg-blue-700"
                    >
                      Save
                    </button>
                  )}
                </div>
            </div>
        </div>
    </div>
  );
};

export default EditStopCheckerStep; 