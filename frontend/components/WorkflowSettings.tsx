'use client';

import React, { useState, useEffect } from 'react';
import { 
  Workflow, 
  WorkflowWithDetails,
  TriggerType, 
  getAvailableTriggerTypes, 
  setWorkflowTrigger, 
  removeWorkflowTrigger,
  updateWorkflowTrigger,
  getWorkflowDetails,
  removeWorkflowStep,
  updateWorkflowStep,
  WorkflowStep,
} from '../services/workflows_api';
import CreateStepModal from './CreateStepModal';
import StepEditor from './workflow/StepEditor';
import TriggerSettings from './workflow/TriggerSettings';
import StepTypeHelp from './help/StepTypeHelp';
import { HelpCircle } from 'lucide-react';

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
  const [showTriggerSelector, setShowTriggerSelector] = useState(false);
  const [showStepSelector, setShowStepSelector] = useState(false);
  const [isHelpPanelOpen, setIsHelpPanelOpen] = useState(false);

  // Trigger settings editing state
  const [editingTrigger, setEditingTrigger] = useState<any>(null);

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

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (showStepSelector && !(event.target as Element).closest('.step-selector')) {
        setShowStepSelector(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showStepSelector]);

  const handleSetTrigger = async (triggerTypeId: string) => {
    if (!triggerTypeId) return;
    
    setIsLoading(true);
    setSaveStatus('saving');
    
    try {
      const updatedWorkflow = await setWorkflowTrigger(workflow.uuid, triggerTypeId);
      console.log('[WorkflowSettings] Received updated workflow after setting trigger:', updatedWorkflow);
      if (updatedWorkflow) {
        setSaveStatus('saved');
        setDetailedWorkflow(updatedWorkflow);
        onWorkflowUpdate(updatedWorkflow);
        setShowTriggerSelector(false);
        setSelectedTriggerType('');
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

  // Save trigger settings
  const handleSaveTriggerSettings = async (filterRules: any) => {
    if (!detailedWorkflow?.trigger) return;
    
    console.log('[WorkflowSettings] handleSaveTriggerSettings called with:', filterRules);
    setIsLoading(true);
    setSaveStatus('saving');

    try {
      console.log(`[WorkflowSettings] Calling updateWorkflowTrigger for workflow ${workflow.uuid}`);
      const updatedWorkflow = await updateWorkflowTrigger(workflow.uuid, filterRules);
      console.log('[WorkflowSettings] Received response from updateWorkflowTrigger:', updatedWorkflow);

      if (updatedWorkflow) {
        setSaveStatus('saved');
        setDetailedWorkflow(updatedWorkflow);
        onWorkflowUpdate(updatedWorkflow);
        setEditingTrigger(null);
        setTimeout(() => setSaveStatus('idle'), 2000);
      } else {
        setSaveStatus('error');
        console.error('[WorkflowSettings] updateWorkflowTrigger returned null or undefined.');
      }
    } catch (error) {
      console.error('Error saving trigger settings:', error);
      setSaveStatus('error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleTriggerClick = () => {
    if (!detailedWorkflow?.trigger) {
      setShowTriggerSelector(true);
    } else {
      // Open trigger settings when clicking on existing trigger
      setEditingTrigger(detailedWorkflow.trigger);
    }
  };

  const handleTriggerSelectorCancel = () => {
    setShowTriggerSelector(false);
    setSelectedTriggerType('');
  };

  const handleStepSelectorCancel = () => {
    setShowStepSelector(false);
  };

  if (isFetchingDetails) {
    return <div className="p-6">Loading workflow details...</div>;
  }

  if (!detailedWorkflow) {
    return <div className="p-6 text-red-500">Could not load workflow details.</div>;
  }

  const hasTrigger = Boolean(detailedWorkflow.trigger);

  return (
    <>
      <div className="p-6">
        <h2 className="text-2xl font-bold mb-4">{detailedWorkflow.name}</h2>
        <p className="text-gray-600 mb-6">{detailedWorkflow.description}</p>
      
      <div className="mb-6">
        {hasTrigger ? (
          <div>
            <div 
              className="border border-gray-300 rounded-lg p-8 bg-white hover:bg-gray-50 transition-colors relative cursor-pointer"
              onClick={handleTriggerClick}
            >
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleRemoveTrigger();
                }}
                disabled={isLoading}
                className="absolute top-2 right-2 text-gray-400 hover:text-red-600 w-6 h-6 flex items-center justify-center disabled:opacity-50"
              >
                ×
              </button>
              <div className="text-center">
                <h3 className="text-lg font-semibold text-gray-800 mb-2">
                  {(() => {
                    const triggerType = triggerTypes.find(t => t.initial_data_description === detailedWorkflow.trigger?.initial_data_description);
                    return triggerType ? triggerType.name : 'Trigger Active';
                  })()}
                </h3>
                <p className="text-sm text-gray-600">
                  {(() => {
                    const triggerType = triggerTypes.find(t => t.initial_data_description === detailedWorkflow.trigger?.initial_data_description);
                    return triggerType ? triggerType.description : 'This workflow has a trigger configured.';
                  })()}
                </p>
              </div>
            </div>
            
            {/* Trigger Settings */}
            {editingTrigger && (
              <TriggerSettings
                trigger={editingTrigger}
                onSave={handleSaveTriggerSettings}
                onCancel={() => setEditingTrigger(null)}
                isLoading={isLoading}
              />
            )}
          </div>
        ) : (
          <div>
            <div 
              className="border-2 border-dashed border-gray-300 rounded-lg p-8 bg-white cursor-pointer hover:bg-gray-50 transition-colors"
              onClick={handleTriggerClick}
            >
              <div className="text-center">
                <p className="text-gray-500 text-lg">Create Trigger</p>
              </div>
            </div>
            
                         {showTriggerSelector && (
               <div className="mt-4 p-4 bg-white border border-gray-300 rounded-lg relative">
                 <button
                   onClick={handleTriggerSelectorCancel}
                   className="absolute top-2 right-2 text-gray-400 hover:text-gray-600 w-6 h-6 flex items-center justify-center"
                   disabled={isLoading}
                 >
                   ×
                 </button>
                 <h4 className="text-lg font-semibold mb-4">Select Trigger Type</h4>
                 <div className="space-y-4">
                   <div>
                     <label htmlFor="trigger-select" className="block text-sm font-medium text-gray-700 mb-2">
                       Trigger Type
                     </label>
                     <select
                       id="trigger-select"
                       value={selectedTriggerType}
                       onChange={(e) => {
                         const value = e.target.value;
                         setSelectedTriggerType(value);
                         if (value) {
                           handleSetTrigger(value);
                         }
                       }}
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
                   
                   {selectedTriggerType && (
                     <div className="p-3 bg-blue-50 border border-blue-200 rounded-md">
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
      
      {/* Add Step Button - Show after trigger if no steps, or after last step if steps exist */}
      {hasTrigger && detailedWorkflow.steps.length === 0 && (
        <div className="mb-6">
          <div className="flex justify-center">
            <div className="relative step-selector">
              <button
                onClick={() => setShowStepSelector(!showStepSelector)}
                className="w-12 h-12 bg-white border-2 border-gray-300 rounded-full flex items-center justify-center hover:bg-gray-50 transition-colors"
              >
                +
              </button>
              
              {showStepSelector && (
                <div className="absolute top-14 left-1/2 transform -translate-x-1/2 bg-white border border-gray-300 rounded-lg shadow-lg z-10 min-w-48">
                  <div className="py-2">
                    <button
                      onClick={() => {
                        setIsAddStepModalOpen(true);
                        setShowStepSelector(false);
                      }}
                      className="w-full px-4 py-2 text-left hover:bg-gray-100 text-sm"
                    >
                      add LLM
                    </button>
                    <button
                      onClick={() => {
                        setIsAddStepModalOpen(true);
                        setShowStepSelector(false);
                      }}
                      className="w-full px-4 py-2 text-left hover:bg-gray-100 text-sm"
                    >
                      add Agent
                    </button>
                    <button
                      onClick={() => {
                        setIsAddStepModalOpen(true);
                        setShowStepSelector(false);
                      }}
                      className="w-full px-4 py-2 text-left hover:bg-gray-100 text-sm"
                    >
                      add Stop Workflow Check
                    </button>
                    <div className="px-4 py-2 border-t border-gray-200">
                      <button 
                        onClick={() => setIsHelpPanelOpen(true)}
                        className="flex items-center text-xs text-blue-500 hover:underline"
                      >
                        <HelpCircle size={14} className="mr-1" />
                        Should I use an LLM or an Agent?
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      
      {/* Step Editor */}
      {editingStep && (
        <div className="mb-6">
          <StepEditor
            key={editingStep.uuid}
            step={editingStep}
            workflowSteps={detailedWorkflow.steps}
            onSave={handleUpdateStep}
            onCancel={() => setEditingStep(null)}
            hasTrigger={hasTrigger}
          />
        </div>
      )}
      
      {/* Existing Steps */}
      {detailedWorkflow.steps.length > 0 && !editingStep && (
        <div className="space-y-4">
          {detailedWorkflow.steps.map((step, index) => (
            <div 
              key={step.uuid} 
              className="bg-white border rounded-lg p-6 cursor-pointer hover:bg-gray-50 transition-colors relative"
              onClick={() => setEditingStep(step)}
            >
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDeleteStep(step.uuid);
                }}
                className="absolute top-2 right-2 text-gray-400 hover:text-red-600 w-6 h-6 flex items-center justify-center"
              >
                ×
              </button>
              <div className="flex items-center">
                <span className="text-gray-500 font-bold text-lg mr-4">{index + 1}</span>
                <div>
                  <p className="font-semibold">{step.name}</p>
                </div>
              </div>
              <div className="absolute bottom-2 right-2 flex items-center space-x-2">
                <span className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full">
                  {step.type.replace('_', ' ')}
                </span>
                {('model' in step) && (
                  <span className="px-2 py-1 bg-blue-100 text-blue-600 text-xs rounded-full">
                    {step.model.split('/').pop()?.split(':')[0] || step.model}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Step Button - Show after steps when steps exist */}
      {hasTrigger && detailedWorkflow.steps.length > 0 && !editingStep && (
        <div className="mt-6">
          <div className="flex justify-center">
            <div className="relative step-selector">
              <button
                onClick={() => setShowStepSelector(!showStepSelector)}
                className="w-12 h-12 bg-white border-2 border-gray-300 rounded-full flex items-center justify-center hover:bg-gray-50 transition-colors"
              >
                +
              </button>
              
              {showStepSelector && (
                <div className="absolute top-14 left-1/2 transform -translate-x-1/2 bg-white border border-gray-300 rounded-lg shadow-lg z-10 min-w-48">
                  <div className="py-2">
                    <button
                      onClick={() => {
                        setIsAddStepModalOpen(true);
                        setShowStepSelector(false);
                      }}
                      className="w-full px-4 py-2 text-left hover:bg-gray-100 text-sm"
                    >
                      add LLM
                    </button>
                    <button
                      onClick={() => {
                        setIsAddStepModalOpen(true);
                        setShowStepSelector(false);
                      }}
                      className="w-full px-4 py-2 text-left hover:bg-gray-100 text-sm"
                    >
                      add Agent
                    </button>
                    <button
                      onClick={() => {
                        setIsAddStepModalOpen(true);
                        setShowStepSelector(false);
                      }}
                      className="w-full px-4 py-2 text-left hover:bg-gray-100 text-sm"
                    >
                      add Stop Workflow Check
                    </button>
                    <div className="px-4 py-2 border-t border-gray-200">
                      <button 
                        onClick={() => setIsHelpPanelOpen(true)}
                        className="flex items-center text-xs text-blue-500 hover:underline"
                      >
                        <HelpCircle size={14} className="mr-1" />
                        Should I use an LLM or an Agent?
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

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
      
      {/* Help Sidebar */}
      <div className={`fixed top-0 right-0 h-full transition-all duration-300 ease-in-out bg-white shadow-lg border-l overflow-y-auto z-50 ${isHelpPanelOpen ? 'w-full max-w-2xl' : 'w-0'}`}>
        {isHelpPanelOpen && <StepTypeHelp onClose={() => setIsHelpPanelOpen(false)} />}
      </div>
    </>
  );
};

export default WorkflowSettings; 