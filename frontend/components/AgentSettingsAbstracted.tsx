'use client';
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Agent, updateAgent, generateLabelDescriptions, applyTemplateDefaults } from '../services/api';
import DynamicFieldRenderer from './DynamicFieldRenderer';
import { set } from 'lodash';

interface AgentSettingsAbstractedProps {
  agent: Agent | null;
  onAgentUpdate: () => void;
}

const AgentSettingsAbstracted: React.FC<AgentSettingsAbstractedProps> = ({ agent, onAgentUpdate }) => {
  const [paramValues, setParamValues] = useState<{ [key: string]: any } | undefined>(agent?.param_values);
  const [isPaused, setIsPaused] = useState(agent?.paused ?? false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [isDirty, setIsDirty] = useState(false);
  const [generationStatus, setGenerationStatus] = useState<'idle' | 'generating' | 'done' | 'error'>('idle');
  const initialState = useRef<{ paramValues: any; isPaused: boolean } | null>(null);

  const handleSave = useCallback(async () => {
    if (!agent) return;

    setSaveStatus('saving');
    const agentToSave = { ...agent, param_values: paramValues, paused: isPaused };

    try {
      await updateAgent(agentToSave);
      setSaveStatus('saved');
      onAgentUpdate();
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (error) {
      console.error('Error saving agent:', error);
      setSaveStatus('error');
    }
  }, [agent, onAgentUpdate, paramValues, isPaused]);

  const handleGenerateDescriptions = useCallback(async () => {
    if (!agent) return;

    setGenerationStatus('generating');
    try {
      const updatedAgent = await generateLabelDescriptions(agent.uuid);
      if (updatedAgent) {
        onAgentUpdate(); // This will refetch agents and update the UI
      } else {
        throw new Error("API did not return an updated agent.");
      }
    } catch (error) {
      console.error('Error during description generation:', error);
      setGenerationStatus('error');
    } finally {
      setGenerationStatus('idle');
    }
  }, [agent, onAgentUpdate]);

  const handleAddExampleLabels = useCallback(async () => {
    if (!agent) return;
    try {
      const updatedAgent = await applyTemplateDefaults(agent.uuid);
      if (updatedAgent) {
        onAgentUpdate();
      } else {
        throw new Error("API did not return an updated agent after applying defaults.");
      }
    } catch (error) {
      console.error('Error applying template defaults:', error);
      // Optionally set an error state here
    }
  }, [agent, onAgentUpdate]);

  useEffect(() => {
    const initialParamValues = agent?.param_values;
    const initialIsPaused = agent?.paused ?? false;

    setParamValues(initialParamValues);
    setIsPaused(initialIsPaused);

    initialState.current = {
      paramValues: JSON.parse(JSON.stringify(initialParamValues || {})),
      isPaused: initialIsPaused,
    };
    setIsDirty(false);
    setSaveStatus('idle');
  }, [agent]);

  useEffect(() => {
    if (!initialState.current) return;

    const paramValuesChanged = JSON.stringify(initialState.current.paramValues) !== JSON.stringify(paramValues);
    const isPausedChanged = initialState.current.isPaused !== isPaused;

    setIsDirty(paramValuesChanged || isPausedChanged);
  }, [paramValues, isPaused]);

  useEffect(() => {
    if (initialState.current === null) return;
    if (initialState.current.isPaused !== isPaused) {
      handleSave();
    }
  }, [isPaused, handleSave]);

  const handleValueChange = (path: string, value: any) => {
    setParamValues(prevValues => {
      const newValues = { ...prevValues };
      set(newValues, path, value);
      return newValues;
    });
  };

  const handlePauseChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setIsPaused(!e.target.checked);
  };
  
  if (!agent) {
    return <div className="p-8 text-gray-500">Select an agent to view its settings.</div>;
  }

  const EMAIL_LABELER_TEMPLATE_ID = "2db09718-6bec-44cb-9360-778364ff6e81";

  const SaveButton = () => (
    <button
      onClick={handleSave}
      className="px-3 py-1 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
      disabled={!isDirty || saveStatus === 'saving'}
    >
      {saveStatus === 'saving' ? 'Saving...' : saveStatus === 'saved' ? 'Saved!' : 'Save'}
    </button>
  );

  const GenerateDescriptionsButton = () => {
    if (agent?.template_id !== EMAIL_LABELER_TEMPLATE_ID) {
      return null;
    }
    return (
      <button
        onClick={handleGenerateDescriptions}
        className="px-3 py-1 text-sm bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed ml-4"
        disabled={generationStatus === 'generating'}
      >
        {generationStatus === 'generating' ? 'Generating... This can take 30 seconds-ish' : 'Auto-generate Descriptions'}
      </button>
    );
  };

  const AddExampleLabelsButton = () => (
    <button
      onClick={handleAddExampleLabels}
      className="px-3 py-1 text-sm bg-green-600 text-white rounded-md hover:bg-green-700"
    >
      Add Example Labels
    </button>
  );

  const hasListLikeField = agent.param_schema?.some(f => f.type === 'list' || f.type === 'key_value_field_one_line');
  const isEmailLabeler = agent.template_id === EMAIL_LABELER_TEMPLATE_ID;
  const hasNoRules = !paramValues?.labeling_rules || paramValues.labeling_rules.length === 0;

  if (isEmailLabeler && hasNoRules) {
    return (
      <div className="flex-1 p-8 overflow-y-auto">
        <div className="max-w-7xl mx-auto">
          <div className="mb-6 p-4 border rounded-lg bg-gray-50">
            <h1 className="text-2xl font-bold mb-4 border-b pb-2">{agent.name}</h1>
            <p className="mt-4 text-sm text-gray-600">{agent.description}</p>
          </div>
          <div className="text-center p-8 border-2 border-dashed rounded-lg">
            <h2 className="text-xl font-semibold mb-4">Choose how to get started</h2>
            <p className="text-gray-600 mb-6">
              You can either generate descriptions from the labels already in your email inbox, or start with our pre-defined examples.
            </p>
            <div className="flex justify-center items-start space-x-4">
              <div className="flex flex-col items-center">
                <GenerateDescriptionsButton />
                <p className="text-xs text-gray-500 mt-2 max-w-xs">
                  This will scan the labels in your inbox and use AI to write descriptions.
                  Make sure you have enough emails with labels for this to work well.
                </p>
              </div>
              <div className="flex flex-col items-center">
                <AddExampleLabelsButton />
                <p className="text-xs text-gray-500 mt-2 max-w-xs">
                  This will add a list of common labels like "invoices" and "newsletters" to get you started.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 p-8 overflow-y-auto">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6 p-4 border rounded-lg bg-gray-50">
          <h1 className="text-2xl font-bold mb-4 border-b pb-2">{agent.name}</h1>
          <div className="flex items-center">
            <label htmlFor="paused-toggle-abstracted" className="flex items-center cursor-pointer">
              <div className="relative">
                <input
                  type="checkbox"
                  id="paused-toggle-abstracted"
                  className="sr-only peer"
                  checked={!isPaused}
                  onChange={handlePauseChange}
                />
                <div className="w-11 h-6 bg-gray-200 rounded-full peer peer-focus:ring-2 peer-focus:ring-blue-500 peer-checked:bg-green-600"></div>
                <div className="absolute left-1 top-1 bg-white border-gray-300 border w-4 h-4 rounded-full transition-transform peer-checked:translate-x-full"></div>
              </div>
              <span className="ml-3 text-sm font-medium text-gray-900">
                {isPaused ? 'Agent is Paused' : 'Agent is Active'}
              </span>
            </label>
            <GenerateDescriptionsButton />
          </div>
          <p className="mt-4 text-sm text-gray-600">{agent.description}</p>
        </div>

        <div className="space-y-8">
            {agent.param_schema?.map(field => {
                const isListLike = field.type === 'list' || field.type === 'key_value_field_one_line';
                return (
                    <DynamicFieldRenderer
                        key={field.parameter_key}
                        field={field}
                        value={paramValues?.[field.parameter_key]}
                        onChange={handleValueChange}
                        path={field.parameter_key}
                        footer={isListLike ? <SaveButton /> : null}
                    />
                );
            })}
        </div>
        {!hasListLikeField && (
            <div className="mt-8 flex justify-end">
                <SaveButton />
            </div>
        )}
      </div>
    </div>
  );
};

export default AgentSettingsAbstracted; 