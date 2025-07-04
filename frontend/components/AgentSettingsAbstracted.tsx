'use client';
import React, { useState, useEffect } from 'react';
import { Agent, updateAgent } from '../services/api';
import DynamicFieldRenderer from './DynamicFieldRenderer';
import { set } from 'lodash';

interface AgentSettingsAbstractedProps {
  agent: Agent | null;
  onAgentUpdate: () => void;
}

const AgentSettingsAbstracted: React.FC<AgentSettingsAbstractedProps> = ({ agent, onAgentUpdate }) => {
  const [paramValues, setParamValues] = useState<{ [key: string]: any } | undefined>(agent?.param_values);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  useEffect(() => {
    setParamValues(agent?.param_values);
  }, [agent]);

  const handleValueChange = (path: string, value: any) => {
    setParamValues(prevValues => {
      const newValues = { ...prevValues };
      set(newValues, path, value);
      return newValues;
    });
  };

  const handleSave = async () => {
    if (!agent) return;

    setSaveStatus('saving');
    const agentToSave = { ...agent, param_values: paramValues };

    try {
      await updateAgent(agentToSave);
      setSaveStatus('saved');
      onAgentUpdate();
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (error) {
      console.error('Error saving agent:', error);
      setSaveStatus('error');
    }
  };
  
  if (!agent) {
    return <div className="p-8 text-gray-500">Select an agent to view its settings.</div>;
  }

  const SaveButton = () => (
    <button
      onClick={handleSave}
      className="px-3 py-1 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
      disabled={saveStatus === 'saving'}
    >
      {saveStatus === 'saving' ? 'Saving...' : saveStatus === 'saved' ? 'Saved!' : 'Save'}
    </button>
  );

  return (
    <div className="flex-1 p-8 overflow-y-auto">
      <div className="max-w-7xl mx-auto">
        <div className="sticky top-0 z-10 bg-white pt-4 pb-4 mb-6 flex justify-between items-center border-b">
          <h1 className="text-2xl font-bold">{agent.name} (Abstracted)</h1>
          <SaveButton />
        </div>
        
        <div className="space-y-8">
            {agent.param_schema?.map(field => (
                <DynamicFieldRenderer
                    key={field.parameter_key}
                    field={field}
                    value={paramValues?.[field.parameter_key]}
                    onChange={handleValueChange}
                    path={field.parameter_key}
                />
            ))}
        </div>
      </div>
    </div>
  );
};

export default AgentSettingsAbstracted; 