'use client';
import React, { useState, useEffect, useCallback } from 'react';
import { createWorkflow, createWorkflowFromTemplate, getWorkflowTemplates, Workflow, Template, WorkflowFromTemplateResponse } from '../services/workflows_api';

interface CreateWorkflowModalProps {
  isOpen: boolean;
  onClose: () => void;
  onWorkflowCreated: (response: WorkflowFromTemplateResponse) => void;
}

const CreateWorkflowModal: React.FC<CreateWorkflowModalProps> = ({ isOpen, onClose, onWorkflowCreated }) => {
  const [view, setView] = useState<'options' | 'scratch'>('options');
  const [workflowName, setWorkflowName] = useState('');
  const [templates, setTemplates] = useState<Template[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const resetAndClose = useCallback(() => {
    setWorkflowName('');
    setError(null);
    setView('options');
    setIsProcessing(false);
    onClose();
  }, [onClose]);

  useEffect(() => {
    if (isOpen) {
      fetchTemplates();
      const handleKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Escape') {
          resetAndClose();
        }
      };
      document.addEventListener('keydown', handleKeyDown);
      return () => {
        document.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [isOpen, resetAndClose]);

  const fetchTemplates = async () => {
    try {
      const fetchedTemplates = await getWorkflowTemplates();
      setTemplates(fetchedTemplates);
    } catch (err) {
      console.error('Failed to fetch templates:', err);
    }
  };

  const handleCreateFromScratch = async () => {
    if (!workflowName.trim()) {
      setError('Workflow name is required.');
      return;
    }
    setError(null);
    setIsProcessing(true);
    try {
      const newWorkflow = await createWorkflow({ name: workflowName, description: '' });
      if (newWorkflow) {
        onWorkflowCreated({ workflow: newWorkflow });
        resetAndClose();
      } else {
        throw new Error('API returned null');
      }
    } catch (err) {
      setError('Failed to create workflow.');
      console.error(err);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCreateFromTemplate = async (templateId: string) => {
    setError(null);
    setIsProcessing(true);
    try {
      const newWorkflowResponse = await createWorkflowFromTemplate(templateId);
      if (newWorkflowResponse) {
        onWorkflowCreated(newWorkflowResponse);
        resetAndClose();
      } else {
        throw new Error('API returned null');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to create from template.');
      console.error(err);
    } finally {
      setIsProcessing(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-center z-50" onClick={resetAndClose}>
      <div className="bg-white rounded-lg p-8 w-full max-w-4xl relative" onClick={(e) => e.stopPropagation()}>
        <button onClick={resetAndClose} className="absolute top-3 right-4 text-gray-500 hover:text-gray-800 text-2xl leading-none">&times;</button>
        <h2 className="text-2xl font-bold mb-6 text-center">Create New Workflow</h2>
        {error && <p className="text-red-500 text-sm mb-4 text-center">{error}</p>}
        {isProcessing && <p className="text-blue-500 text-sm mb-4 text-center">Processing...</p>}

        {view === 'options' && !isProcessing && (
          <div>
            {templates.length > 0 && (
              <div className="mb-8">
                <p className="text-center text-gray-500 mb-4">Start from a template</p>
                <div className={`grid grid-cols-1 sm:grid-cols-2 ${templates.length > 2 ? 'lg:grid-cols-3' : ''} gap-4 max-h-96 overflow-y-auto p-1`}>
                  {templates.map((template) => (
                    <div
                      key={template.id}
                      onClick={() => handleCreateFromTemplate(template.id)}
                      className="py-4 border rounded-lg hover:bg-gray-100 cursor-pointer flex flex-col h-full transition-all duration-200 ease-in-out transform hover:-translate-y-1"
                    >
                      <p className="font-semibold text-lg px-4">{template.name}</p>
                      <div className="border-t border-gray-200 mt-2 mb-3"></div>
                      <p className="text-sm text-gray-600 flex-grow px-4">{template.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="text-center text-gray-500">
              ... or&nbsp;
              <button
                onClick={() => setView('scratch')}
                className="px-4 py-2 text-sm bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300"
              >
                create from scratch
              </button>
            </div>
          </div>
        )}

        {view === 'scratch' && !isProcessing && (
          <div>
            <input
              type="text"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              placeholder="Enter workflow name"
              className="w-full p-2 border rounded-md mb-4"
              autoFocus
            />
            <div className="flex justify-end space-x-2">
              <button onClick={() => setView('options')} className="px-4 py-2 text-sm bg-gray-200 rounded-md">Back</button>
              <button onClick={handleCreateFromScratch} className="px-4 py-2 text-sm bg-blue-500 text-white rounded-md">Create</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default CreateWorkflowModal; 