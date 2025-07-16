'use client';

import React, { useState } from 'react';
import { X } from 'lucide-react';

interface CreateEvaluationTemplateModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const CreateEvaluationTemplateModal: React.FC<CreateEvaluationTemplateModalProps> = ({ isOpen, onClose }) => {
  const [step, setStep] = useState(1);

  if (!isOpen) {
    return null;
  }

  const renderStepContent = () => {
    switch (step) {
      case 1:
        return (
          <div>
            <h3 className="text-lg font-medium text-gray-900">Step 1: Configure Data Source</h3>
            <p className="mt-2 text-sm text-gray-600">
              Here, the user will select the IMAP tool and provide parameters like folder, count, and labels.
            </p>
          </div>
        );
      case 2:
        return (
          <div>
            <h3 className="text-lg font-medium text-gray-900">Step 2: Map Data Fields</h3>
            <p className="mt-2 text-sm text-gray-600">
              The user will see a sample data record and map fields to "Prompt Input" and "Ground Truth".
            </p>
          </div>
        );
      case 3:
        return (
          <div>
            <h3 className="text-lg font-medium text-gray-900">Step 3: Snapshot and Save</h3>
            <p className="mt-2 text-sm text-gray-600">
              The user will name the template and confirm to fetch the data and save the snapshot.
            </p>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl transform transition-all">
        <div className="p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-gray-800">Create Evaluation Template</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X size={24} />
            </button>
          </div>
          <div className="mt-6">
            {renderStepContent()}
          </div>
        </div>
        <div className="bg-gray-50 px-6 py-4 flex justify-between items-center rounded-b-lg">
          <div>
            {step > 1 && (
              <button
                onClick={() => setStep(step - 1)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
              >
                Previous
              </button>
            )}
          </div>
          <div>
            {step < 3 ? (
              <button
                onClick={() => setStep(step + 1)}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700"
              >
                Next
              </button>
            ) : (
              <button
                onClick={() => {
                  // TODO: Final save logic
                  alert('Saving template...');
                  onClose();
                }}
                className="px-4 py-2 text-sm font-medium text-white bg-green-600 border border-transparent rounded-md hover:bg-green-700"
              >
                Create Template
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CreateEvaluationTemplateModal; 