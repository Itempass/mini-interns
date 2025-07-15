'use client';
import React, { useState } from 'react';
import { Workflow, deleteWorkflow } from '../services/workflows_api';
import { Plus, MoreVertical, Trash2 } from 'lucide-react';
import CreateWorkflowModal from './CreateWorkflowModal';

interface WorkflowSidebarProps {
  workflows: Workflow[];
  onSelectWorkflow: (workflow: Workflow | null) => void;
  selectedWorkflow: Workflow | null;
  onWorkflowsUpdate: () => void;
}

const WorkflowSidebar: React.FC<WorkflowSidebarProps> = ({ workflows, onSelectWorkflow, selectedWorkflow, onWorkflowsUpdate }) => {
  const [isCreateModalOpen, setCreateModalOpen] = useState(false);
  const [menuOpenFor, setMenuOpenFor] = useState<string | null>(null);

  const handleWorkflowCreated = () => {
    onWorkflowsUpdate();
    setCreateModalOpen(false);
  };

  const handleDeleteWorkflow = async (uuid: string) => {
    if (window.confirm('Are you sure you want to delete this workflow?')) {
      const success = await deleteWorkflow(uuid);
      if (success) {
        onWorkflowsUpdate();
        setMenuOpenFor(null);
      } else {
        alert('Failed to delete workflow.');
      }
    }
  };

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">Workflows</h2>
        <button onClick={() => setCreateModalOpen(true)} className="p-1 text-gray-500 hover:text-black">
          <Plus className="h-6 w-6" />
        </button>
      </div>
      <ul>
        {workflows.map((workflow) => (
          <li key={workflow.uuid} className="mb-2 relative">
            <div className="flex items-center justify-between p-2 rounded-md hover:bg-gray-100">
              <span
                className={`flex-grow cursor-pointer flex items-center ${selectedWorkflow?.uuid === workflow.uuid ? 'font-semibold' : ''}`}
                onClick={() => onSelectWorkflow(workflow)}
              >
                <span className={`h-2 w-2 rounded-full mr-2 shrink-0 ${workflow.is_active ? 'bg-green-500' : 'bg-gray-400'}`}></span>
                {workflow.name}
              </span>
              <button
                onClick={() => setMenuOpenFor(menuOpenFor === workflow.uuid ? null : workflow.uuid)}
                className="p-1 rounded-md hover:bg-gray-200 ml-1"
                aria-label="Workflow options"
              >
                <MoreVertical size={16} />
              </button>
            </div>
            {menuOpenFor === workflow.uuid && (
              <div className="absolute right-0 mt-1 w-32 bg-white border rounded-md shadow-lg z-10">
                <button
                  onClick={() => handleDeleteWorkflow(workflow.uuid)}
                  className="flex items-center w-full px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                >
                  <Trash2 size={14} className="mr-2" />
                  Delete
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <CreateWorkflowModal
        isOpen={isCreateModalOpen}
        onClose={() => setCreateModalOpen(false)}
        onWorkflowCreated={handleWorkflowCreated}
      />
    </div>
  );
};

export default WorkflowSidebar; 