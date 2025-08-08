import React, { useEffect, useState, useRef } from 'react';
import { RAGStep, WorkflowStep } from '../../../services/workflows_api';
import { listVectorDatabases, VectorDatabase } from '../../../services/rag_api';
import PlaceholderTextEditor from './PlaceholderTextEditor';
import NoReferencesHelp from '../../help/NoReferencesHelp';
import { AlertCircle, Copy, Calendar } from 'lucide-react';
import { useTimezone } from '../../../hooks/useTimezone';

interface EditRAGStepProps {
  step: RAGStep;
  onSave: (step: WorkflowStep) => void;
  onCancel: () => void;
  hasTrigger?: boolean;
  precedingSteps?: WorkflowStep[];
}

const EditRAGStep: React.FC<EditRAGStepProps> = ({ step, onSave, onCancel, hasTrigger = false, precedingSteps = [] }) => {
  const [currentStep, setCurrentStep] = useState<RAGStep>(step);
  const [vectorDbs, setVectorDbs] = useState<VectorDatabase[]>([]);
  const [isLoadingDbs, setIsLoadingDbs] = useState(true);
  const [initialPrompt, setInitialPrompt] = useState(step.system_prompt);
  const [isPromptDirty, setIsPromptDirty] = useState(false);
  const [showCopyMessage, setShowCopyMessage] = useState(false);
  const copyTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [showNoReferencesHelp, setShowNoReferencesHelp] = useState(false);
  const { timezone } = useTimezone();

  const hasNoReferences =
    (hasTrigger || (precedingSteps && precedingSteps.length > 0)) &&
    !currentStep.system_prompt.includes('<<trigger_output>>') &&
    !currentStep.system_prompt.includes('<<step_output.');

  useEffect(() => {
    const fetchDbs = async () => {
      setIsLoadingDbs(true);
      try {
        const dbs = await listVectorDatabases();
        setVectorDbs(dbs);
        if (!currentStep.vectordb_uuid && dbs.length > 0) {
          const updated = { ...currentStep, vectordb_uuid: dbs[0].uuid };
          setCurrentStep(updated);
          onSave(updated);
        }
      } finally {
        setIsLoadingDbs(false);
      }
    };
    fetchDbs();
  }, []);

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    };
  }, []);

  const handlePromptChange = (newValue: string) => {
    setCurrentStep({ ...currentStep, system_prompt: newValue });
    setIsPromptDirty(newValue !== initialPrompt);
  };

  const handlePromptSave = () => {
    onSave(currentStep);
    setInitialPrompt(currentStep.system_prompt);
    setIsPromptDirty(false);
  };

  const handleDbChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const updated = { ...currentStep, vectordb_uuid: e.target.value };
    setCurrentStep(updated);
    onSave(updated);
  };

  const handleRerankToggle = (e: React.ChangeEvent<HTMLInputElement>) => {
    const updated = { ...currentStep, rerank: e.target.checked };
    setCurrentStep(updated);
    onSave(updated);
  };

  const handleTopKChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseInt(e.target.value || '0', 10);
    const updated = { ...currentStep, top_k: isNaN(value) ? 5 : value };
    setCurrentStep(updated);
    onSave(updated);
  };

  const copyPlaceholder = async (placeholder: string) => {
    try {
      await navigator.clipboard.writeText(placeholder);
      setShowCopyMessage(true);
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
      copyTimeoutRef.current = setTimeout(() => setShowCopyMessage(false), 3000);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  };

  const copyDatePlaceholder = () => {
    if (timezone) {
      copyPlaceholder(`<<CURRENT_DATE.${timezone}>>`);
    } else {
      copyPlaceholder('<<CURRENT_DATE.UTC>>');
      console.warn('Timezone not yet available, falling back to UTC for placeholder.');
    }
  };

  return (
    <div className="p-6 space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700">Query / Prompt</label>
        {hasNoReferences && (
          <div className="mt-1">
            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-red-800 bg-red-100 rounded-full cursor-pointer hover:bg-red-200"
              onClick={() => setShowNoReferencesHelp(true)}
            >
              <AlertCircle size={12} />
              No references to previous outputs found!
            </span>
          </div>
        )}
        <div className="relative">
          <PlaceholderTextEditor
            value={currentStep.system_prompt}
            onChange={handlePromptChange}
            onSave={handlePromptSave}
            placeholder="e.g., Find emails mentioning shipment delays and summarize."
            className="mt-1"
            hasTrigger={hasTrigger}
            precedingSteps={precedingSteps}
            showSaveButton={isPromptDirty}
            rows={8}
          />
          {showCopyMessage && (
            <div className="absolute bottom-3 left-1/2 transform -translate-x-1/2 px-2 py-1 bg-white bg-opacity-40 backdrop-blur-sm text-gray-800 text-xs rounded border border-gray-300 border-opacity-40 shadow-sm">
              Copied! Paste inside your prompt
            </div>
          )}
        </div>
        {(hasTrigger || precedingSteps.length > 0 || timezone) && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <p className="text-sm text-gray-600">Insert placeholders:</p>
            <button
              type="button"
              onClick={copyDatePlaceholder}
              className="px-3 py-1 bg-purple-100 text-purple-800 text-sm rounded-full hover:bg-purple-200 transition-colors flex items-center gap-1"
            >
              <Calendar size={12} /> current date
            </button>
            {hasTrigger && (
              <button
                type="button"
                onClick={() => copyPlaceholder('<<trigger_output>>')}
                className="px-3 py-1 bg-green-100 text-green-800 text-sm rounded-full hover:bg-green-200 transition-colors flex items-center gap-1"
              >
                <Copy size={12} /> trigger output
              </button>
            )}
            {precedingSteps.map((precedingStep, index) => (
              <button
                key={precedingStep.uuid}
                type="button"
                onClick={() => copyPlaceholder(`<<step_output.${precedingStep.uuid}>>`)}
                className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full hover:bg-blue-200 transition-colors flex items-center gap-1"
              >
                <Copy size={12} /> step {index + 2} output
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700">Vector Database</label>
        <select
          value={currentStep.vectordb_uuid || ''}
          onChange={handleDbChange}
          className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
          disabled={isLoadingDbs}
        >
          {isLoadingDbs ? (
            <option>Loading...</option>
          ) : vectorDbs.length > 0 ? (
            vectorDbs.map((db) => (
              <option key={db.uuid} value={db.uuid}>
                {db.name} ({db.provider})
              </option>
            ))
          ) : (
            <option value="">No vector databases configured</option>
          )}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={!!currentStep.rerank}
              onChange={handleRerankToggle}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
            />
            <span className="text-sm text-gray-700">Apply reranking</span>
          </label>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700">Top K</label>
          <input
            type="number"
            min={1}
            value={currentStep.top_k}
            onChange={handleTopKChange}
            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
      </div>

      {/* Help Sidebar */}
      <div className={`fixed top-0 right-0 h-full transition-all duration-300 ease-in-out bg-white shadow-lg border-l overflow-y-auto z-20 ${showNoReferencesHelp ? 'w-full max-w-2xl' : 'w-0'}`}>
        {showNoReferencesHelp && <NoReferencesHelp onClose={() => setShowNoReferencesHelp(false)} />}
      </div>
    </div>
  );
};

export default EditRAGStep; 