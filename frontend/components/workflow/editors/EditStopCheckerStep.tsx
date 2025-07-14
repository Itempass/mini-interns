
import React, { useState } from 'react';
import { StopWorkflowCheckerStep, WorkflowStep, StopWorkflowCondition } from '../../../services/workflows_api';

interface EditStopCheckerStepProps {
  step: StopWorkflowCheckerStep;
  precedingSteps: WorkflowStep[];
  onSave: (step: WorkflowStep) => void;
  onCancel: () => void;
}

const OPERATORS: StopWorkflowCondition['operator'][] = ["equals", "not_equals", "contains", "greater_than", "less_than"];

const EditStopCheckerStep: React.FC<EditStopCheckerStepProps> = ({ step, precedingSteps, onSave, onCancel }) => {
  const [currentStep, setCurrentStep] = useState(step);

  const handleConditionChange = (index: number, field: keyof StopWorkflowCondition, value: any) => {
    const newConditions = [...currentStep.stop_conditions];
    newConditions[index] = { ...newConditions[index], [field]: value };
    setCurrentStep({ ...currentStep, stop_conditions: newConditions });
  };

  const handleAddCondition = () => {
    const newCondition: StopWorkflowCondition = {
      step_definition_uuid: precedingSteps.length > 0 ? precedingSteps[0].uuid : '',
      extraction_json_path: '',
      operator: 'equals',
      target_value: ''
    };
    setCurrentStep({ ...currentStep, stop_conditions: [...currentStep.stop_conditions, newCondition] });
  };

  const handleRemoveCondition = (index: number) => {
    const newConditions = currentStep.stop_conditions.filter((_, i) => i !== index);
    setCurrentStep({ ...currentStep, stop_conditions: newConditions });
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
            <label className="block text-sm font-medium text-gray-700">Stop Conditions</label>
            <div className="mt-2 space-y-4">
                {currentStep.stop_conditions.map((condition, index) => (
                    <div key={index} className="p-4 border rounded-md bg-white space-y-3 relative">
                         <button 
                            onClick={() => handleRemoveCondition(index)}
                            className="absolute top-2 right-2 text-red-500 hover:text-red-700"
                            aria-label="Remove condition"
                        >
                           &times;
                        </button>
                        <div>
                            <label className="text-xs font-medium text-gray-600">Step to Check</label>
                            <select
                                value={condition.step_definition_uuid}
                                onChange={(e) => handleConditionChange(index, 'step_definition_uuid', e.target.value)}
                                className="mt-1 block w-full text-sm px-3 py-2 border border-gray-300 rounded-md"
                                disabled={precedingSteps.length === 0}
                            >
                                {precedingSteps.length > 0 ? precedingSteps.map(pStep => (
                                    <option key={pStep.uuid} value={pStep.uuid}>{pStep.name} ({pStep.type})</option>
                                )) : <option>No previous steps available</option>}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-medium text-gray-600">JSONPath from Output</label>
                            <input
                                type="text"
                                value={condition.extraction_json_path}
                                onChange={(e) => handleConditionChange(index, 'extraction_json_path', e.target.value)}
                                className="mt-1 block w-full text-sm px-3 py-2 border border-gray-300 rounded-md font-mono"
                                placeholder="e.g., $.summary"
                            />
                        </div>
                        <div className="flex items-center space-x-2">
                            <div className="flex-1">
                                <label className="text-xs font-medium text-gray-600">Operator</label>
                                <select
                                    value={condition.operator}
                                    onChange={(e) => handleConditionChange(index, 'operator', e.target.value)}
                                    className="mt-1 block w-full text-sm px-3 py-2 border border-gray-300 rounded-md"
                                >
                                    {OPERATORS.map(op => <option key={op} value={op}>{op}</option>)}
                                </select>
                            </div>
                            <div className="flex-1">
                                <label className="text-xs font-medium text-gray-600">Target Value</label>
                                <input
                                    type="text"
                                    value={condition.target_value}
                                    onChange={(e) => handleConditionChange(index, 'target_value', e.target.value)}
                                    className="mt-1 block w-full text-sm px-3 py-2 border border-gray-300 rounded-md"
                                />
                            </div>
                        </div>
                    </div>
                ))}
                <button
                    onClick={handleAddCondition}
                    className="w-full px-4 py-2 text-sm font-medium text-blue-700 bg-blue-100 border border-transparent rounded-md hover:bg-blue-200"
                >
                    + Add Condition
                </button>
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