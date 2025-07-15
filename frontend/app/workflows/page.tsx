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
import { Search, Bot, Workflow as WorkflowIcon, Loader2 } from 'lucide-react';

const WorkflowsPage = () => {
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [isLogsExpanded, setIsLogsExpanded] = useState(false);
  const [isAgentBusy, setIsAgentBusy] = useState(false);

  const fetchWorkflows = async (newlyCreated?: Workflow) => {
    const freshWorkflows = await getWorkflows();
    setWorkflows(freshWorkflows);

    if (newlyCreated) {
      setSelectedWorkflow(newlyCreated);
    } else if (selectedWorkflow) {
      const updatedSelectedWorkflow = freshWorkflows.find(w => w.uuid === selectedWorkflow.uuid);
      setSelectedWorkflow(updatedSelectedWorkflow || (freshWorkflows.length > 0 ? freshWorkflows[0] : null));
    } else if (freshWorkflows.length > 0) {
      setSelectedWorkflow(freshWorkflows[0]);
    } else {
      setSelectedWorkflow(null);
    }
  };
  
  const handleWorkflowUpdate = () => {
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
          <main className="flex-1 flex flex-col gap-4 p-4 bg-gray-100 overflow-y-auto">
            {selectedWorkflow ? (
              <>
                <div className={`flex-1 flex-row gap-4 overflow-hidden ${isLogsExpanded ? 'hidden' : 'flex'}`}>
                    <div className="flex-1 overflow-y-auto bg-white border border-gray-200 rounded-lg">
                      <WorkflowSettings
                        key={selectedWorkflow.uuid}
                        workflow={selectedWorkflow}
                        onWorkflowUpdate={handleWorkflowUpdate}
                      />
                    </div>
                    <div className="flex-1 flex flex-col">
                      <WorkflowChat
                        workflowId={selectedWorkflow.uuid}
                        onWorkflowUpdate={handleWorkflowUpdate}
                        onBusyStatusChange={setIsAgentBusy}
                      />
                    </div>
                </div>

                {isLogsExpanded && (
                  <div 
                    className="flex flex-row gap-4 cursor-pointer"
                    onClick={() => setIsLogsExpanded(false)}
                  >
                    <div className="flex-1 p-4 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition">
                        <h3 className="text-lg font-semibold flex items-center">
                            <WorkflowIcon className="w-5 h-5 mr-2" />
                            {selectedWorkflow.name}
                        </h3>
                    </div>
                    <div className="flex-1 p-4 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition">
                        <div className="flex items-center justify-between">
                          <h3 className="text-lg font-semibold flex items-center">
                              <Bot className="w-5 h-5 mr-2" />
                              Workflow Agent
                          </h3>
                          {isAgentBusy && <Loader2 className="w-5 h-5 animate-spin text-gray-500" />}
                        </div>
                    </div>
                  </div>
                )}

                {/* Workflow Logs Section */}
                <div className={`bg-white border border-gray-200 rounded-lg ${isLogsExpanded ? 'flex-1 flex flex-col' : 'flex-shrink-0'}`}>
                  <div 
                    className="p-4 border-b border-gray-200 cursor-pointer"
                    onClick={() => setIsLogsExpanded(true)}
                  >
                    <h3 className="text-lg font-semibold flex items-center">
                      <Search className="w-5 h-5 mr-2" />
                      Workflow Logs
                    </h3>
                  </div>
                  {isLogsExpanded && (
                    <div className="flex-1 p-4 overflow-y-auto">
                      {/* Body for logs will go here in the future */}
                      <p>Logs will appear here when this view is expanded.</p>
                    </div>
                  )}
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