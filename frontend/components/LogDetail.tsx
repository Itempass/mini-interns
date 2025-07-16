'use client';
import React from 'react';
import { LogEntry, LogMessage } from '../services/api';

const roleToColorMap: { [key: string]: string } = {
  system: 'bg-gray-200 text-gray-800',
  user: 'bg-blue-100 text-blue-900',
  assistant: 'bg-green-100 text-green-900',
  tool: 'bg-yellow-100 text-yellow-900',
};

const formatToolArguments = (args: string) => {
  try {
    const parsed = JSON.parse(args);
    return JSON.stringify(parsed, null, 2);
  } catch (e) {
    return args;
  }
};

const DetailRow: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="flex flex-col sm:flex-row mb-2">
    <span className="font-bold w-full sm:w-[200px] mr-2 text-gray-600">{label}:</span>
    <span className="break-words w-full">{value || <span className="text-gray-400">N/A</span>}</span>
  </div>
);

interface LogDetailProps {
  log: LogEntry;
}

const LogDetail: React.FC<LogDetailProps> = ({ log }) => {
  if (!log) {
    return <div className="p-5 font-sans">Loading log...</div>;
  }

  const duration = log.end_time ? new Date(log.end_time).getTime() - new Date(log.start_time).getTime() : null;

  return (
    <div className="p-5 max-w-6xl mx-auto font-sans">
      <div className="p-6 mb-6 bg-gray-50 border border-gray-200 rounded-lg shadow-sm">
        <h3 className="mt-0 mb-4 text-xl font-semibold text-gray-800">Log Details</h3>
        <DetailRow label="Log ID" value={log.id} />
        <DetailRow label="Type" value={log.log_type} />
        <DetailRow label="Start Time" value={new Date(log.start_time).toLocaleString()} />
        <DetailRow label="End Time" value={log.end_time ? new Date(log.end_time).toLocaleString() : 'N/A'} />
        <DetailRow label="Duration" value={duration !== null ? `${(duration / 1000).toFixed(2)}s` : 'N/A'} />
        <DetailRow label="Anonymized" value={log.anonymized ? 'Yes' : 'No'} />
        <DetailRow label="Needs Review" value={log.needs_review ? 'Yes' : 'No'} />
        <DetailRow label="Feedback" value={log.feedback} />
      </div>

      <div className="p-6 mb-6 bg-gray-50 border border-gray-200 rounded-lg shadow-sm">
        <h3 className="mt-0 mb-4 text-xl font-semibold text-gray-800">Workflow & Step Info</h3>
        <DetailRow label="Workflow Name" value={log.workflow_name} />
        <DetailRow label="Workflow ID" value={log.workflow_id} />
        <DetailRow label="Workflow Instance ID" value={log.workflow_instance_id} />
        <hr className="my-4" />
        <DetailRow label="Step Name" value={log.step_name} />
        <DetailRow label="Step ID" value={log.step_id} />
        <DetailRow label="Step Instance ID" value={log.step_instance_id} />
      </div>
      
      <div className="p-6 mb-6 bg-gray-50 border border-gray-200 rounded-lg shadow-sm">
        <h3 className="mt-0 mb-4 text-xl font-semibold text-gray-800">Reference String</h3>
        <pre className="p-3 bg-white border border-gray-200 rounded whitespace-pre-wrap font-mono text-sm">{log.reference_string || 'N/A'}</pre>
      </div>

      {log.messages && log.messages.length > 0 && (
        <div className="mt-8">
          <h3 className="text-xl font-semibold mb-4">Messages</h3>
          <div className="space-y-6">
            {log.messages.map((message, index) => (
              <div key={index} className="p-5 border rounded-lg bg-white shadow-sm">
                <div className="flex justify-between items-center mb-4">
                  <span className={`font-semibold px-3 py-1 rounded-md text-sm ${roleToColorMap[message.role] || 'bg-gray-100'}`}>
                    {message.role === 'tool' ? `tool: ${message.name}` : message.role}
                  </span>
                </div>
                {message.content && (
                  <pre className="text-gray-800 whitespace-pre-wrap leading-relaxed font-sans">{message.content}</pre>
                )}
                {message.tool_calls && (
                  <div className="mt-4">
                    <h4 className="text-md font-semibold text-gray-800 mb-2">Tool Calls</h4>
                    {message.tool_calls.map((toolCall: any, i: number) => (
                      <div key={i} className="mt-2 p-3 bg-gray-50 rounded font-mono text-sm">
                        <div className="text-gray-700"><strong>Function:</strong> {toolCall.function.name}</div>
                        <div className="text-gray-700">
                          <strong>Arguments:</strong>
                          <pre className="whitespace-pre-wrap bg-gray-100 p-2 rounded mt-1">
                            {formatToolArguments(toolCall.function.arguments)}
                          </pre>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="p-4 mt-8 bg-gray-800 border border-gray-700 rounded-lg">
        <h3 className="mt-0 mb-4 text-xl font-semibold text-white">Full Log Data (JSON)</h3>
        <pre className="p-4 overflow-x-auto text-sm bg-gray-900 text-green-300 border border-gray-700 rounded max-h-[600px] overflow-y-auto font-mono">
          {JSON.stringify(log, null, 2)}
        </pre>
      </div>
    </div>
  );
};

export default LogDetail; 