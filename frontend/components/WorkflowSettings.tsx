'use client';

import React, { useState, useEffect } from 'react';
import { 
  Workflow, 
  WorkflowWithDetails,
  TriggerType, 
  getAvailableTriggerTypes, 
  setWorkflowTrigger, 
  removeWorkflowTrigger,
  getWorkflowDetails,
  removeWorkflowStep,
  updateWorkflowStep,
  WorkflowStep,
} from '../services/workflows_api';
import CreateStepModal from './CreateStepModal';
import StepEditor from './workflow/StepEditor';

interface WorkflowSettingsProps {
  workflow: Workflow;
  onWorkflowUpdate: (updatedWorkflow: WorkflowWithDetails) => void;
}

const WorkflowSettings: React.FC<WorkflowSettingsProps> = ({ workflow, onWorkflowUpdate }) => {
  const [detailedWorkflow, setDetailedWorkflow] = useState<WorkflowWithDetails | null>(null);
  const [triggerTypes, setTriggerTypes] = useState<TriggerType[]>([]);
  const [selectedTriggerType, setSelectedTriggerType] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [isFetchingDetails, setIsFetchingDetails] = useState(true);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [isAddStepModalOpen, setIsAddStepModalOpen] = useState(false);
  const [editingStep, setEditingStep] = useState<WorkflowStep | null>(null);

  const fetchDetails = async () => {
    if (workflow) {
      console.log(`[WorkflowSettings] Fetching details for workflow: ${workflow.uuid}`);
      setIsFetchingDetails(true);
      const details = await getWorkflowDetails(workflow.uuid);
      console.log(`[WorkflowSettings] Received details for workflow: ${workflow.uuid}`, details);
      setDetailedWorkflow(details);
      setIsFetchingDetails(false);
    }
  };

  useEffect(() => {
    const fetchTriggerTypes = async () => {
      const types = await getAvailableTriggerTypes();
      setTriggerTypes(types);
    };
    fetchTriggerTypes();
  }, []);

  useEffect(() => {
    fetchDetails();
  }, [workflow]);

  const handleSetTrigger = async () => {
    if (!selectedTriggerType) return;
    
    setIsLoading(true);
    setSaveStatus('saving');
    
    try {
      const updatedWorkflow = await setWorkflowTrigger(workflow.uuid, selectedTriggerType);
      console.log('[WorkflowSettings] Received updated workflow after setting trigger:', updatedWorkflow);
      if (updatedWorkflow) {
        setSaveStatus('saved');
        setDetailedWorkflow(updatedWorkflow);
        onWorkflowUpdate(updatedWorkflow);
        setTimeout(() => setSaveStatus('idle'), 2000);
      } else {
        setSaveStatus('error');
      }
    } catch (error) {
      console.error('Error setting trigger:', error);
      setSaveStatus('error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRemoveTrigger = async () => {
    if (!detailedWorkflow?.trigger?.uuid) return;
    
    setIsLoading(true);
    setSaveStatus('saving');
    
    try {
      const updatedWorkflow = await removeWorkflowTrigger(workflow.uuid);
      console.log('[WorkflowSettings] Received updated workflow after removing trigger:', updatedWorkflow);
      if (updatedWorkflow) {
        setSaveStatus('saved');
        setDetailedWorkflow(updatedWorkflow);
        onWorkflowUpdate(updatedWorkflow);
        setSelectedTriggerType('');
        setTimeout(() => setSaveStatus('idle'), 2000);
      } else {
        setSaveStatus('error');
      }
    } catch (error) {
      console.error('Error removing trigger:', error);
      setSaveStatus('error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteStep = async (stepId: string) => {
    if (!detailedWorkflow) return;

    const isSuccess = await removeWorkflowStep(detailedWorkflow.uuid, stepId);
    if (isSuccess) {
      fetchDetails(); // Refetch details to update the UI
    } else {
      alert('Failed to delete step.'); // Simple error handling
    }
  };

  const handleUpdateStep = async (stepToUpdate: WorkflowStep) => {
    const updatedStep = await updateWorkflowStep(stepToUpdate);
    if (updatedStep) {
      setEditingStep(null);
      fetchDetails(); // Refetch to show updated data
    } else {
      alert('Failed to update step.');
    }
  };

  if (isFetchingDetails) {
    return <div className="p-6">Loading workflow details...</div>;
  }

  if (!detailedWorkflow) {
    return <div className="p-6 text-red-500">Could not load workflow details.</div>;
  }

  const hasTrigger = Boolean(detailedWorkflow.trigger);

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">{detailedWorkflow.name}</h2>
      <p className="text-gray-600 mb-6">{detailedWorkflow.description}</p>
      
      <div className="bg-white border rounded-lg p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Trigger Configuration</h3>
        
        {hasTrigger ? (
          <div className="space-y-4">
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-green-500 rounded-full"></div>
              <span className="text-green-700 font-medium">Trigger Active</span>
            </div>
            <p className="text-sm text-gray-600">
              This workflow has a trigger configured and will run automatically when the trigger conditions are met.
            </p>
            <button
              onClick={handleRemoveTrigger}
              disabled={isLoading}
              className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {isLoading ? 'Removing...' : 'Remove Trigger'}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-gray-400 rounded-full"></div>
              <span className="text-gray-600 font-medium">No Trigger Configured</span>
            </div>
            <p className="text-sm text-gray-600">
              Select a trigger type to automatically run this workflow when certain events occur.
            </p>
            
            <div className="flex items-end space-x-4">
              <div className="flex-1">
                <label htmlFor="trigger-select" className="block text-sm font-medium text-gray-700 mb-2">
                  Trigger Type
                </label>
                <select
                  id="trigger-select"
                  value={selectedTriggerType}
                  onChange={(e) => setSelectedTriggerType(e.target.value)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  disabled={isLoading}
                >
                  <option value="">Select a trigger type...</option>
                  {triggerTypes.map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.name}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleSetTrigger}
                disabled={!selectedTriggerType || isLoading}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                {isLoading ? 'Setting...' : 'Set Trigger'}
              </button>
            </div>
            
            {selectedTriggerType && (
              <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-md">
                {(() => {
                  const selectedType = triggerTypes.find(t => t.id === selectedTriggerType);
                  return selectedType ? (
                    <div>
                      <p className="text-sm font-medium text-blue-800">{selectedType.name}</p>
                      <p className="text-sm text-blue-600 mt-1">{selectedType.description}</p>
                      <p className="text-xs text-blue-500 mt-2">
                        <strong>Initial Data:</strong> {selectedType.initial_data_description}
                      </p>
                    </div>
                  ) : null;
                })()}
              </div>
            )}
          </div>
        )}
        
        {saveStatus === 'saved' && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-md">
            <p className="text-sm text-green-700">✓ Trigger configuration saved successfully!</p>
          </div>
        )}
        
        {saveStatus === 'error' && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md">
            <p className="text-sm text-red-700">✗ Failed to save trigger configuration. Please try again.</p>
          </div>
        )}
      </div>
      
      <div className="bg-white border rounded-lg p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">Workflow Steps</h3>
          <button
            onClick={() => setIsAddStepModalOpen(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400"
          >
            Add Step
          </button>
        </div>
        
        {editingStep ? (
          <StepEditor
            key={editingStep.uuid}
            step={editingStep}
            workflowSteps={detailedWorkflow.steps}
            onSave={handleUpdateStep}
            onCancel={() => setEditingStep(null)}
          />
        ) : detailedWorkflow.steps.length > 0 ? (
          <ol className="space-y-4">
            {detailedWorkflow.steps.map((step, index) => (
              <li key={step.uuid} className="p-4 border rounded-md bg-gray-50 flex items-center justify-between">
                <div className="flex items-center">
                  <span className="text-gray-500 font-bold text-lg mr-4">{index + 1}</span>
                  <div>
                    <p className="font-semibold">{step.name}</p>
                    <p className="text-sm text-gray-500">{step.type}</p>
                  </div>
                </div>
                <div>
                  <button 
                    onClick={() => setEditingStep(step)}
                    className="text-sm text-blue-600 hover:underline mr-4"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDeleteStep(step.uuid)}
                    className="text-sm text-red-600 hover:underline"
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <div className="text-center py-8 px-4 border-2 border-dashed rounded-lg">
            <p className="text-gray-500">This workflow has no steps.</p>
            <p className="text-sm text-gray-400 mt-1">Click "Add Step" to get started.</p>
          </div>
        )}
      </div>

      <CreateStepModal
        workflowId={detailedWorkflow.uuid}
        isOpen={isAddStepModalOpen}
        onClose={() => setIsAddStepModalOpen(false)}
        onStepCreated={(updatedWorkflow) => {
          console.log('[WorkflowSettings] Received updated workflow from CreateStepModal:', updatedWorkflow);
          setDetailedWorkflow(updatedWorkflow);
          onWorkflowUpdate(updatedWorkflow);
        }}
      />
    </div>
  );
};

export default WorkflowSettings; 