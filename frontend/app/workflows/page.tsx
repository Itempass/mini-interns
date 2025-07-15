'use client';
import React, { useState, useEffect } from 'react';
import TopBar from '../../components/TopBar';
import WorkflowSidebar from '../../components/WorkflowSidebar';
import WorkflowSettings from '../../components/WorkflowSettings';
import { Workflow, WorkflowWithDetails, getWorkflows } from '../../services/workflows_api';
import VersionCheck from '../../components/VersionCheck';
import ConnectionStatusIndicator from '../../components/ConnectionStatusIndicator';
import NoWorkflowsView from '../../components/NoWorkflowsView';
import WorkflowChat from '../../components/WorkflowChat';

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
    // We will now just refetch everything to ensure consistency.
    fetchWorkflows();
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
          <main className="flex-1 flex flex-row gap-4 p-4 bg-gray-100 overflow-hidden">
            {selectedWorkflow ? (
              <>
                <div className="flex-1 overflow-y-auto bg-white border border-gray-200 rounded-lg">
                  <WorkflowSettings
                    key={selectedWorkflow.uuid}
                    workflow={selectedWorkflow}
                    onWorkflowUpdate={fetchWorkflows}
                  />
                </div>
                <div className="flex-1">
                  <WorkflowChat
                    workflowId={selectedWorkflow.uuid}
                    onWorkflowUpdate={fetchWorkflows}
                  />
                </div>
              </>
            ) : (
              <div className="w-full">
                <NoWorkflowsView />
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
};

export default WorkflowsPage; 