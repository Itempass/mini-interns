import React from 'react';
import { X } from 'lucide-react';

interface NoReferencesHelpProps {
  onClose: () => void;
}

const NoReferencesHelp: React.FC<NoReferencesHelpProps> = ({ onClose }) => {
  return (
    <div className="p-6 h-full">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold">How Step Outputs Work</h2>
        <button 
          onClick={onClose}
          className="text-gray-500 hover:text-gray-700 transition-colors"
          aria-label="Close"
        >
          <X size={24} />
        </button>
      </div>
      <div className="space-y-4">
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <h3 className="font-semibold text-blue-900 mb-2">Key Concept: Outputs Are Not Automatic</h3>
          <p className="text-sm text-blue-800">
            The output of a previous step (like a trigger or another LLM/Agent step) is **not** automatically passed to the next step's system prompt. You must explicitly tell the workflow where to put that data.
          </p>
        </div>
        
        <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
          <h3 className="font-semibold text-gray-900 mb-2">How to Use Previous Outputs</h3>
          <p className="text-sm text-gray-700 mb-3">
            To use the output from a previous step, you must insert its placeholder into the system prompt. You can do this by clicking the placeholder buttons below the text editor.
          </p>
          <div className="space-y-2 text-sm">
            <p>
              <strong>1. Click a placeholder button:</strong>
            </p>
            <div className="flex items-center gap-2">
              <span className="px-3 py-1 bg-green-100 text-green-800 text-sm rounded-full">trigger output</span>
              <span className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full">step 2 output</span>
            </div>
            <p className="mt-2">
              <strong>2. Copy the placeholder:</strong> The text (e.g., <code>&lt;&lt;trigger_output&gt;&gt;</code>) will be copied to your clipboard.
            </p>
            <p>
              <strong>3. Paste it into the system prompt:</strong> Place the placeholder exactly where you want the previous step's output to appear.
            </p>
          </div>
        </div>
        
        <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
          <h3 className="font-semibold text-yellow-900 mb-2">Example</h3>
          <p className="text-sm text-yellow-800">
            If a trigger provides an email, your system prompt might look like this:
          </p>
          <pre className="mt-2 p-2 bg-gray-100 rounded text-sm font-mono">
            Please summarize the following email and identify the sender:<br/><br/>
            {`<<trigger_output>>`}
          </pre>
          <p className="mt-2 text-sm text-yellow-800">
            At runtime, <code>&lt;&lt;trigger_output&gt;&gt;</code> will be replaced with the actual email content.
          </p>
        </div>
      </div>
    </div>
  );
};

export default NoReferencesHelp; 