'use client';
import React, { useState, useEffect } from 'react';
import TopBar from '../../components/TopBar';
import WorkflowSidebar from '../../components/WorkflowSidebar';
import WorkflowSettings from '../../components/WorkflowSettings';
import { Workflow, WorkflowWithDetails, getWorkflows } from '../../services/workflows_api';

import ConnectionStatusIndicator from '../../components/ConnectionStatusIndicator';
import NoWorkflowsView from '../../components/NoWorkflowsView';
import WorkflowChat from '../../components/WorkflowChat';
import { Search, Bot, Workflow as WorkflowIcon, Loader2 } from 'lucide-react';
import LogsList from '../../components/LogsList';
import LogDetail from '../../components/LogDetail';
import { LogEntry, getLogEntry } from '../../services/api';

const WorkflowsPage = () => {
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [isLogsExpanded, setIsLogsExpanded] = useState(false);
  const [isAgentBusy, setIsAgentBusy] = useState(false);

  // State for log detail modal
  const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);
  const [isLogModalOpen, setIsLogModalOpen] = useState(false);
  const [isLoadingLog, setIsLoadingLog] = useState(false);

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
    // When changing workflow, ensure the logs are not expanded
    setIsLogsExpanded(false);
  };

  const handleSelectLog = async (logId: string) => {
    setSelectedLogId(logId);
    setIsLogModalOpen(true);
    setIsLoadingLog(true);
    const data = await getLogEntry(logId);
    if (data) {
      setSelectedLog(data);
    } else {
      console.error("Could not load log");
    }
    setIsLoadingLog(false);
  };

  const handleCloseLogModal = () => {
    setIsLogModalOpen(false);
    setSelectedLogId(null);
    setSelectedLog(null);
  };

  return (
    <div className="flex flex-col h-screen relative" style={{
      backgroundImage: 'radial-gradient(#E5E7EB 1px, transparent 1px)',
      backgroundSize: '24px 24px'
    }}>
      <div className="flex flex-col flex-grow overflow-hidden">
        <TopBar />
        <div className="flex flex-1 overflow-hidden gap-4 p-4">
          <div className="w-64 flex-shrink-0 flex flex-col bg-white border border-gray-300 rounded-lg overflow-hidden shadow-md">
            <div className="flex flex-col flex-grow overflow-y-auto">
              <WorkflowSidebar 
                workflows={workflows}
                onSelectWorkflow={handleSelectWorkflow} 
                selectedWorkflow={selectedWorkflow} 
                onWorkflowsUpdate={fetchWorkflows}
              />
            </div>
            <div className="border-t border-gray-200">
              <ConnectionStatusIndicator />
            </div>
          </div>
          <main className="flex-1 flex flex-col gap-4 overflow-y-auto">
            {selectedWorkflow ? (
              <>
                <div className={`flex-1 flex-row gap-4 overflow-hidden ${isLogsExpanded ? 'hidden' : 'flex'}`}>
                    <div className="flex-1 flex flex-col bg-white border border-gray-300 rounded-lg shadow-md">
                      <WorkflowChat
                        workflowId={selectedWorkflow.uuid}
                        onWorkflowUpdate={handleWorkflowUpdate}
                        onBusyStatusChange={setIsAgentBusy}
                      />
                    </div>
                    <div className="flex-1 overflow-y-auto bg-white border border-gray-300 rounded-lg shadow-md">
                      <WorkflowSettings
                        key={selectedWorkflow.uuid}
                        workflow={selectedWorkflow}
                        onWorkflowUpdate={handleWorkflowUpdate}
                      />
                    </div>
                </div>

                {isLogsExpanded && (
                  <div 
                    className="flex flex-row gap-4 cursor-pointer"
                    onClick={() => setIsLogsExpanded(false)}
                  >
                    <div className="flex-1 p-4 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition shadow-md">
                        <div className="flex items-center justify-between">
                          <h3 className="text-lg font-semibold flex items-center">
                              <Bot className="w-5 h-5 mr-2" />
                              Workflow Agent
                          </h3>
                          {isAgentBusy && <Loader2 className="w-5 h-5 animate-spin text-gray-500" />}
                        </div>
                    </div>
                    <div className="flex-1 p-4 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition shadow-md">
                        <h3 className="text-lg font-semibold flex items-center">
                            <WorkflowIcon className="w-5 h-5 mr-2" />
                            {selectedWorkflow.name}
                        </h3>
                    </div>
                  </div>
                )}

                {/* Workflow Logs Section */}
                <div className={`bg-white border border-gray-300 rounded-lg shadow-md ${isLogsExpanded ? 'flex-1 flex flex-col' : 'flex-shrink-0'}`}>
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
                      {selectedWorkflow && (
                        <LogsList
                          key={selectedWorkflow.uuid}
                          workflowId={selectedWorkflow.uuid}
                          onSelectLog={handleSelectLog}
                          logType={'workflow'}
                        />
                      )}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="w-full h-full flex-1">
                <NoWorkflowsView />
              </div>
            )}
          </main>
        </div>
      </div>

      {isLogModalOpen && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-gray-900 bg-opacity-75 flex justify-center items-center">
          <div className="bg-white rounded-lg shadow-2xl w-full max-w-6xl h-[90vh] flex flex-col relative">
            <div className="flex justify-between items-center p-4 border-b">
              <h2 className="text-xl font-bold">Log Details</h2>
              <button onClick={handleCloseLogModal} className="text-gray-500 hover:text-gray-800 text-3xl font-bold">&times;</button>
            </div>
            <div className="p-5 overflow-y-auto flex-grow">
              {isLoadingLog ? (
                <div>Loading...</div>
              ) : selectedLog ? (
                <LogDetail log={selectedLog} />
              ) : (
                <div>Log not found.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default WorkflowsPage; 