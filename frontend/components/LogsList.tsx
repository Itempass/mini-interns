'use client';
import React, { useState, useEffect, Fragment } from 'react';
import { getGroupedLogEntries, LogEntry, GroupedLog } from '../services/api';

interface LogsListProps {
  onSelectLog: (logId: string) => void;
  workflowId?: string;
}

const PAGE_SIZE = 20;

const LogsList: React.FC<LogsListProps> = ({ onSelectLog, workflowId }) => {
  const [groupedLogs, setGroupedLogs] = useState<GroupedLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [expandedWorkflows, setExpandedWorkflows] = useState<Record<string, boolean>>({});

  const fetchLogs = async (currentOffset: number, isNewWorkflow: boolean) => {
    setLoading(true);
    const response = await getGroupedLogEntries(PAGE_SIZE, currentOffset, workflowId);
    if (response.workflows.length > 0) {
      setGroupedLogs(prev => isNewWorkflow ? response.workflows : [...prev, ...response.workflows]);
    } else if (isNewWorkflow) {
      setGroupedLogs([]);
    }
    
    if (currentOffset === 0 || (currentOffset + PAGE_SIZE) >= response.total_workflows) {
      setHasMore((currentOffset + PAGE_SIZE) < response.total_workflows);
    }
    setLoading(false);
  };

  useEffect(() => {
    setOffset(0);
    fetchLogs(0, true);
  }, [workflowId]);

  const handleLoadMore = () => {
    const newOffset = offset + PAGE_SIZE;
    setOffset(newOffset);
    fetchLogs(newOffset, false);
  };

  const toggleWorkflow = (workflowInstanceId: string) => {
    setExpandedWorkflows(prev => ({
      ...prev,
      [workflowInstanceId]: !prev[workflowInstanceId]
    }));
  };

  const handleRowClick = (logId: string) => {
    onSelectLog(logId);
  };

  const handleDownload = () => {
    if (groupedLogs.length === 0) {
      return;
    }
    const jsonString = JSON.stringify(groupedLogs, null, 2);
    const blob = new Blob([jsonString], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "logs.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const thClasses = "p-3 text-left font-bold text-white bg-gray-600 border-t border-b border-gray-300";
  const tdClasses = "p-3 border-b border-gray-200 align-top";

  const renderLogRow = (log: LogEntry, isChild: boolean) => {
    const duration = log.end_time ? new Date(log.end_time).getTime() - new Date(log.start_time).getTime() : null;
    const status = log.needs_review ? 'Needs Review' : (log.feedback ? 'Reviewed' : 'OK');
    const isExpanded = log.workflow_instance_id && expandedWorkflows[log.workflow_instance_id];

    const onRowClick = isChild
      ? () => handleRowClick(log.id)
      : () => { if (log.workflow_instance_id) toggleWorkflow(log.workflow_instance_id); };

    return (
      <tr
        key={log.id}
        className={`cursor-pointer ${isChild ? 'bg-gray-50 hover:bg-gray-100' : 'bg-white hover:bg-gray-100'}`}
        onClick={onRowClick}
      >
        <td className={`${tdClasses} ${isChild ? 'pl-8' : ''}`}>
          <div className="flex items-center">
            {!isChild && (
              <span className="mr-2 text-lg w-4 inline-block text-center">
                {isExpanded ? '▼' : '▶'}
              </span>
            )}
            <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
              log.log_type === 'custom_agent' ? 'bg-blue-100 text-blue-800' :
              log.log_type === 'custom_llm' ? 'bg-green-100 text-green-800' :
              log.log_type === 'workflow' ? 'bg-indigo-100 text-indigo-800' :
              'bg-gray-100 text-gray-800'
            }`}>
              {log.log_type.replace(/_/g, ' ')}
            </span>
          </div>
        </td>
        <td className={tdClasses}>{log.workflow_name || log.step_name || 'N/A'}</td>
        <td className={tdClasses}>{new Date(log.start_time).toLocaleString()}</td>
        <td className={tdClasses}>
          {duration !== null ? `${(duration / 1000).toFixed(2)}s` : 'N/A'}
        </td>
         <td className={tdClasses}>
          <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
              status === 'Needs Review' ? 'bg-yellow-100 text-yellow-800' :
              status === 'Reviewed' ? 'bg-green-100 text-green-800' :
              'bg-gray-200 text-gray-800'
          }`}>
              {status}
          </span>
        </td>
        <td className={`${tdClasses} font-mono text-xs max-w-[20ch] overflow-hidden text-ellipsis whitespace-nowrap`} title={log.id}>{log.id}</td>
      </tr>
    );
  };
  
  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="m-0 text-xl font-bold">Logs</h2>
        <button
          onClick={handleDownload}
          disabled={groupedLogs.length === 0}
          className="px-4 py-2 text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:bg-gray-400"
        >
          Download as JSON
        </button>
      </div>
      <div className="overflow-x-auto shadow-md rounded-lg">
        <table className="w-full bg-white border-collapse">
          <thead>
            <tr>
              <th className={`${thClasses} rounded-tl-lg`}>Type</th>
              <th className={thClasses}>Name</th>
              <th className={thClasses}>Start Time</th>
              <th className={thClasses}>Duration</th>
              <th className={thClasses}>Status</th>
              <th className={`${thClasses} rounded-tr-lg`}>Log ID</th>
            </tr>
          </thead>
          <tbody>
            {groupedLogs.map(({ workflow_log, step_logs }) => (
              <Fragment key={workflow_log.id}>
                {renderLogRow(workflow_log, false)}
                {workflow_log.workflow_instance_id && expandedWorkflows[workflow_log.workflow_instance_id] && (
                  step_logs.map(stepLog => renderLogRow(stepLog, true))
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {loading && <div className="p-5 text-center">Loading...</div>}
      {!loading && hasMore && (
        <div className="mt-5 text-center">
          <button
            onClick={handleLoadMore}
            className="px-6 py-2 text-white bg-green-600 rounded-md hover:bg-green-700"
          >
            Load More
          </button>
        </div>
      )}
      {!loading && groupedLogs.length === 0 && (
        <p className="p-5 text-center bg-white rounded-lg shadow-md mt-4">No logs found.</p>
      )}
    </div>
  );
};

export default LogsList; 