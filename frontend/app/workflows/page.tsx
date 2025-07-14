'use client';
import React, { useState, useEffect } from 'react';
import TopBar from '../../components/TopBar';
import WorkflowSidebar from '../../components/WorkflowSidebar';
import WorkflowSettings from '../../components/WorkflowSettings';
import { Workflow, WorkflowWithDetails, getWorkflows } from '../../services/workflows_api';
import VersionCheck from '../../components/VersionCheck';
import ConnectionStatusIndicator from '../../components/ConnectionStatusIndicator';
import NoWorkflowsView from '../../components/NoWorkflowsView';

const WorkflowsPage = () => {
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);

  const fetchWorkflows = async () => {
    const freshWorkflows = await getWorkflows();
    setWorkflows(freshWorkflows);

    if (selectedWorkflow) {
      const updatedSelectedWorkflow = freshWorkflows.find(w => w.uuid === selectedWorkflow.uuid);
      setSelectedWorkflow(updatedSelectedWorkflow || (freshWorkflows.length > 0 ? freshWorkflows[0] : null));
    } else if (freshWorkflows.length > 0) {
      setSelectedWorkflow(freshWorkflows[0]);
    } else {
      setSelectedWorkflow(null);
    }
  };
  
  const handleWorkflowUpdate = (updatedWorkflow: WorkflowWithDetails) => {
    // This function is now only responsible for updating the list in the sidebar,
    // as the WorkflowSettings component manages its own detailed state.
    setWorkflows(currentWorkflows => 
      currentWorkflows.map(w => 
        w.uuid === updatedWorkflow.uuid 
        ? { ...w, name: updatedWorkflow.name, description: updatedWorkflow.description, is_active: updatedWorkflow.is_active } 
        : w
      )
    );
  };

  useEffect(() => {
    fetchWorkflows();
  }, []);

  const handleSelectWorkflow = (workflow: Workflow | null) => {
    setSelectedWorkflow(workflow);
  };

  return (
    <div className="flex flex-col h-screen bg-white">
      <VersionCheck />
      <div className="flex flex-col flex-grow overflow-hidden">
        <TopBar />
        <div className="flex flex-1 overflow-hidden">
          <div className="w-64 flex-shrink-0 flex flex-col bg-gray-50 border-r border-gray-200">
            <div className="flex flex-col flex-grow overflow-y-auto">
              <WorkflowSidebar 
                workflows={workflows}
                onSelectWorkflow={handleSelectWorkflow} 
                selectedWorkflow={selectedWorkflow} 
                onWorkflowsUpdate={fetchWorkflows}
              />
            </div>
            <ConnectionStatusIndicator />
          </div>
          <main className="flex-1 overflow-y-auto bg-gray-100">
            {selectedWorkflow ? (
                <WorkflowSettings 
                  key={selectedWorkflow.uuid} 
                  workflow={selectedWorkflow} 
                  onWorkflowUpdate={handleWorkflowUpdate} 
                />
            ) : (
              <NoWorkflowsView />
            )}
          </main>
        </div>
      </div>
    </div>
  );
};

export default WorkflowsPage; 