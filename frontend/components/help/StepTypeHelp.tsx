import React from 'react';
import { X } from 'lucide-react';

interface StepTypeHelpProps {
  onClose: () => void;
}

const StepTypeHelp: React.FC<StepTypeHelpProps> = ({ onClose }) => {
  return (
    <div className="p-6 h-full">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold">Step Types Guide</h2>
        <button 
          onClick={onClose}
          className="text-gray-500 hover:text-gray-700 transition-colors"
        >
          <X size={24} />
        </button>
      </div>
      
      <div className="space-y-6">
        <div className="p-4 bg-purple-50 border border-purple-200 rounded-lg">
          <h3 className="font-semibold text-purple-900 mb-2">TLDR</h3>
          <div className="text-sm text-purple-800 space-y-1">
            <p>• <strong>LLM:</strong> Simple text processing without external tools</p>
            <p>• <strong>Agent:</strong> Complex tasks with external tools (emails, APIs, etc.)</p>
            <p>• <strong>Stop Check:</strong> Conditional workflow termination</p>
          </div>
        </div>

        <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
          <h3 className="font-semibold text-gray-900 mb-2">Choosing the Right Step Type</h3>
          <div className="text-sm text-gray-700 space-y-2">
            <p><strong>Start with LLM</strong> if you need simple text processing without external data access.</p>
            <p><strong>Use Agent</strong> when you need to interact with external systems, search data, or use multiple tools.</p>
            <p><strong>Add Stop Checks</strong> to create efficient workflows that don't waste resources on unnecessary steps.</p>
          </div>
        </div>

        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <h3 className="font-semibold text-blue-900 mb-2">LLM Step</h3>
          <p className="text-sm text-blue-800 mb-3">
            Use for simple text processing, analysis, or generation tasks. The LLM receives input and produces text output without access to external tools.
          </p>
          <div className="text-xs text-blue-700">
            <strong>Best for:</strong>
            <ul className="list-disc ml-4 mt-1">
              <li>Text summarization</li>
              <li>Content analysis</li>
              <li>Data transformation</li>
              <li>Simple decision making</li>
            </ul>
          </div>
          <div className="mt-3 text-xs text-blue-700">
            <strong>Example:</strong> "Summarize this email and extract key action items"
          </div>
        </div>

        <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
          <h3 className="font-semibold text-green-900 mb-2">Agent Step</h3>
          <p className="text-sm text-green-800 mb-3">
            Use for complex tasks that require external tools (like searching emails, sending messages, or accessing APIs). Agents can use multiple tools and make decisions about which tools to use.
          </p>
          <div className="text-xs text-green-700">
            <strong>Best for:</strong>
            <ul className="list-disc ml-4 mt-1">
              <li>Email searching and filtering</li>
              <li>API interactions</li>
              <li>Multi-step workflows</li>
              <li>Tool orchestration</li>
            </ul>
          </div>
          <div className="mt-3 text-xs text-green-700">
            <strong>Example:</strong> "Search for recent emails about project X and send a summary to the team"
          </div>
        </div>

        <div className="p-4 bg-orange-50 border border-orange-200 rounded-lg">
          <h3 className="font-semibold text-orange-900 mb-2">Stop Workflow Check</h3>
          <p className="text-sm text-orange-800 mb-3">
            Use to conditionally stop the workflow based on previous step outputs. This allows you to create branching logic and prevent unnecessary processing.
          </p>
          <div className="text-xs text-orange-700">
            <strong>Best for:</strong>
            <ul className="list-disc ml-4 mt-1">
              <li>Conditional workflow termination</li>
              <li>Resource optimization</li>
              <li>Error handling</li>
              <li>Business logic gates</li>
            </ul>
          </div>
          <div className="mt-3 text-xs text-orange-700">
            <strong>Example:</strong> "Stop workflow if no relevant emails were found in the search"
          </div>
        </div>
      </div>
    </div>
  );
};

export default StepTypeHelp; 