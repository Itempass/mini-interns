'use client';
import React, { useState, useEffect, useRef } from 'react';
import { Agent, Tool, updateAgent, getTools, FilterRules, exportAgent } from '../services/api';
import ToolList, { UiTool } from './ToolList';

interface AgentSettingsProps {
  agent: Agent | null;
  onAgentUpdate: () => void;
}

const AgentSettings: React.FC<AgentSettingsProps> = ({ agent, onAgentUpdate }) => {
  const [editableAgent, setEditableAgent] = useState<Agent | null>(agent);
  const [tools, setTools] = useState<UiTool[]>([]);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [isDirty, setIsDirty] = useState(false);
  const initialState = useRef<{ agent: Agent, tools: UiTool[], filterRuleStrings: any } | null>(null);

  const [filterRuleStrings, setFilterRuleStrings] = useState({
    email_blacklist: '',
    email_whitelist: '',
    domain_blacklist: '',
    domain_whitelist: '',
  });
  const [filterErrors, setFilterErrors] = useState({
    email_blacklist: '',
    email_whitelist: '',
    domain_blacklist: '',
    domain_whitelist: '',
  });

  useEffect(() => {
    const initializeState = async () => {
      if (agent) {
        const agentWithDefaults: Agent = {
          ...agent,
          paused: agent.paused ?? false,
          trigger_conditions: agent.trigger_conditions ?? '',
          filter_rules: agent.filter_rules ?? { email_blacklist: [], email_whitelist: [], domain_blacklist: [], domain_whitelist: [] },
          trigger_bypass: agent.trigger_bypass ?? false,
        };
        setEditableAgent(agentWithDefaults);

        const newFilterRuleStrings = {
          email_blacklist: agent.filter_rules?.email_blacklist.join(', ') || '',
          email_whitelist: agent.filter_rules?.email_whitelist.join(', ') || '',
          domain_blacklist: agent.filter_rules?.domain_blacklist.join(', ') || '',
          domain_whitelist: agent.filter_rules?.domain_whitelist.join(', ') || '',
        };
        setFilterRuleStrings(newFilterRuleStrings);

        const availableTools = await getTools();
        const agentTools = agent.tools || {};
        const uiTools: UiTool[] = availableTools.map(tool => {
            const agentToolInfo = agentTools[tool.id];
            return {
                ...tool,
                inputSchema: tool.input_schema,
                serverName: tool.server,
                enabled: agentToolInfo ? agentToolInfo.enabled : false,
                required: agentToolInfo ? agentToolInfo.required : false,
                order: agentToolInfo?.order,
            };
        });
        setTools(uiTools);
        
        initialState.current = {
          agent: agentWithDefaults,
          tools: uiTools,
          filterRuleStrings: newFilterRuleStrings,
        };
        setIsDirty(false);
        setSaveStatus('idle');

      } else {
        setEditableAgent(null);
        setTools([]);
        initialState.current = null;
      }
    };

    initializeState();
  }, [agent]);

  useEffect(() => {
    if (!initialState.current) return;

    const { agent: initialAgentState, tools: initialToolsState, filterRuleStrings: initialFilterStringsState } = initialState.current;

    const agentChanged = JSON.stringify(initialAgentState) !== JSON.stringify(editableAgent);
    const toolsChanged = JSON.stringify(initialToolsState) !== JSON.stringify(tools);
    const filtersChanged = JSON.stringify(initialFilterStringsState) !== JSON.stringify(filterRuleStrings);

    setIsDirty(agentChanged || toolsChanged || filtersChanged);
  }, [editableAgent, tools, filterRuleStrings]);


  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (editableAgent) {
      const target = e.target;
      const value = target.type === 'checkbox' ? (target as HTMLInputElement).checked : target.value;
      setEditableAgent({ ...editableAgent, [e.target.name]: value });
    }
  };

  const handlePauseChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (editableAgent) {
      setEditableAgent({ ...editableAgent, paused: !e.target.checked });
    }
  };

  const validateFilterInput = (name: keyof FilterRules, value: string) => {
    const items = value.split(',').map(item => item.trim()).filter(Boolean);
    let error = '';

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const domainRegex = /^([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$/;

    for (const item of items) {
      if (name.includes('email') && !emailRegex.test(item)) {
        error = `"${item}" is not a valid email.`;
        break;
      }
      if (name.includes('domain') && !domainRegex.test(item)) {
        error = `"${item}" is not a valid domain.`;
        break;
      }
    }
    setFilterErrors(prev => ({ ...prev, [name]: error }));
  };

  const handleFilterRuleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const { name, value } = e.target as { name: keyof FilterRules; value: string };
    setFilterRuleStrings(prev => ({
      ...prev,
      [name]: value,
    }));
    validateFilterInput(name, value);
  };

  const handleToolsChange = (updatedTools: UiTool[]) => {
    setTools(updatedTools);
  };

  const handleSave = async () => {
    if (!editableAgent) return;
    
    if (Object.values(filterErrors).some(err => err)) {
      alert('Please fix the validation errors before saving.');
      return;
    }

    setSaveStatus('saving');

    const agentToolsToSave: { [key: string]: { enabled: boolean; required: boolean; order?: number } } = {};
    const requiredTools = tools.filter(t => t.required);

    tools.forEach(tool => {
      agentToolsToSave[tool.id] = {
        enabled: tool.enabled,
        required: tool.required,
      };
      if (tool.required) {
        agentToolsToSave[tool.id].order = requiredTools.findIndex(t => t.id === tool.id);
      }
    });

    const finalFilterRules: FilterRules = {
      email_blacklist: filterRuleStrings.email_blacklist.split(',').map(item => item.trim()).filter(Boolean),
      email_whitelist: filterRuleStrings.email_whitelist.split(',').map(item => item.trim()).filter(Boolean),
      domain_blacklist: filterRuleStrings.domain_blacklist.split(',').map(item => item.trim()).filter(Boolean),
      domain_whitelist: filterRuleStrings.domain_whitelist.split(',').map(item => item.trim()).filter(Boolean),
    };

    const agentToSave = { ...editableAgent, tools: agentToolsToSave, filter_rules: finalFilterRules };

    try {
      await updateAgent(agentToSave);
      setSaveStatus('saved');
      onAgentUpdate();
      // No need to set dirty to false here, the useEffect on [agent] will handle it
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (error) {
      console.error('Error saving agent:', error);
      setSaveStatus('error');
    }
  };

  const handleExport = async () => {
    if (agent) {
      try {
        await exportAgent(agent.uuid);
      } catch (error) {
        console.error('Error exporting agent:', error);
        alert('Failed to export agent.');
      }
    }
  };

  if (!editableAgent) {
    return <div className="p-8 text-gray-500">Select an agent to view or edit its settings.</div>;
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

  return (
    <div className="flex-1 p-8 overflow-y-auto">
      <div className="max-w-7xl mx-auto">
        <div className="sticky top-0 z-10 bg-white pt-4 pb-4 mb-6 flex justify-between items-center border-b">
          <h1 className="text-2xl font-bold">{editableAgent.name}</h1>
          <button
            onClick={handleExport}
            className="px-3 py-1 text-sm bg-gray-600 text-white rounded-md hover:bg-gray-700"
          >
            Export
          </button>
        </div>
        
        <div className="space-y-8">
          {/* General Settings */}
          <div className="p-4 border rounded-lg bg-gray-50">
            <div className="flex justify-between items-center mb-4 border-b pb-2">
              <h2 className="text-xl font-semibold">General</h2>
              <SaveButton />
            </div>
            <div className="space-y-4 mt-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Name</label>
                <input type="text" name="name" value={editableAgent.name} onChange={handleInputChange} className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Description</label>
                <textarea name="description" value={editableAgent.description} onChange={handleInputChange} rows={2} className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" />
              </div>
              <div className="flex items-center pt-2">
                <label htmlFor="paused-toggle" className="flex items-center cursor-pointer">
                  <div className="relative">
                    <input
                      type="checkbox"
                      id="paused-toggle"
                      name="paused"
                      className="sr-only peer"
                      checked={!editableAgent.paused}
                      onChange={handlePauseChange}
                    />
                    <div className="w-11 h-6 bg-gray-200 rounded-full peer peer-focus:ring-2 peer-focus:ring-blue-500 peer-checked:bg-green-600"></div>
                    <div className="absolute left-1 top-1 bg-white border-gray-300 border w-4 h-4 rounded-full transition-transform peer-checked:translate-x-full"></div>
                  </div>
                  <span className="ml-3 text-sm font-medium text-gray-900">
                    {editableAgent.paused ? 'Agent is Paused' : 'Agent is Active'}
                  </span>
                </label>
              </div>
            </div>
          </div>

          {/* Trigger Settings */}
          <div className="p-4 border rounded-lg bg-gray-50">
            <div className="flex justify-between items-center mb-4 border-b pb-2">
              <h2 className="text-xl font-semibold">Trigger Settings</h2>
              <SaveButton />
            </div>
            <div className="space-y-4 mt-4">
              <div className="flex items-center">
                <input
                  type="checkbox"
                  name="trigger_bypass"
                  id="trigger_bypass"
                  checked={editableAgent.trigger_bypass || false}
                  onChange={handleInputChange}
                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <label htmlFor="trigger_bypass" className="ml-2 block text-sm font-medium text-gray-900">
                  Bypass trigger
                </label>
              </div>

              {!editableAgent.trigger_bypass && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Trigger Instructions</label>
                    <textarea name="trigger_conditions" value={editableAgent.trigger_conditions} onChange={handleInputChange} rows={5} className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" />
                    <p className="text-xs text-gray-600 mt-1">Note: &lt;&lt;CURRENT_DATE&gt;&gt; will be replaced with the current date (YYYY-MM-DD).</p>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Email Blacklist (comma-separated)</label>
                      <textarea name="email_blacklist" value={filterRuleStrings.email_blacklist} onChange={handleFilterRuleChange} rows={2} className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" />
                      <p className="text-xs text-gray-600 mt-1">Stop processing emails from these specific addresses. Ex: spam@example.com, junk@mail.net</p>
                      {filterErrors.email_blacklist && <p className="text-xs text-red-600 mt-1">{filterErrors.email_blacklist}</p>}
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Email Whitelist (comma-separated)</label>
                      <textarea name="email_whitelist" value={filterRuleStrings.email_whitelist} onChange={handleFilterRuleChange} rows={2} className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" />
                      <p className="text-xs text-gray-600 mt-1">If used, only emails from these addresses will proceed. Ex: boss@mycompany.com</p>
                      {filterErrors.email_whitelist && <p className="text-xs text-red-600 mt-1">{filterErrors.email_whitelist}</p>}
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Domain Blacklist (comma-separated)</label>
                      <textarea name="domain_blacklist" value={filterRuleStrings.domain_blacklist} onChange={handleFilterRuleChange} rows={2} className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" />
                      <p className="text-xs text-gray-600 mt-1">Stop processing emails from these domains. Ex: evil-corp.com, bad-actors.org</p>
                      {filterErrors.domain_blacklist && <p className="text-xs text-red-600 mt-1">{filterErrors.domain_blacklist}</p>}
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Domain Whitelist (comma-separated)</label>
                      <textarea name="domain_whitelist" value={filterRuleStrings.domain_whitelist} onChange={handleFilterRuleChange} rows={2} className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" />
                      <p className="text-xs text-gray-600 mt-1">If used, only emails from these domains will proceed. Ex: mycompany.com</p>
                      {filterErrors.domain_whitelist && <p className="text-xs text-red-600 mt-1">{filterErrors.domain_whitelist}</p>}
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Agent Settings */}
          <div className="p-4 border rounded-lg bg-gray-50">
             <div className="flex justify-between items-center mb-4 border-b pb-2">
                <h2 className="text-xl font-semibold">Agent Settings</h2>
                <SaveButton />
            </div>
            <div className="space-y-4 mt-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">User Instructions</label>
                <textarea name="user_instructions" value={editableAgent.user_instructions} onChange={handleInputChange} rows={10} className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" />
                <p className="text-xs text-gray-600 mt-1">Note: &lt;&lt;CURRENT_DATE&gt;&gt; will be replaced with the current date (YYYY-MM-DD).</p>
              </div>
              <div>
                <h3 className="text-lg font-medium text-gray-900 mb-2">Tools</h3>
                <ToolList tools={tools} onToolsChange={handleToolsChange} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentSettings; 