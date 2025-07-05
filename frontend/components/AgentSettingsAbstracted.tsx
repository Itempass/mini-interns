'use client';
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Agent, updateAgent } from '../services/api';
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

  const SaveButton = () => (
    <button
      onClick={handleSave}
      className="px-3 py-1 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
      disabled={!isDirty || saveStatus === 'saving'}
    >
      {saveStatus === 'saving' ? 'Saving...' : saveStatus === 'saved' ? 'Saved!' : 'Save'}
    </button>
  );

  const hasListLikeField = agent.param_schema?.some(f => f.type === 'list' || f.type === 'key_value_field_one_line');

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