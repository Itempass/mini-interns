'use client';
import React, { useState, useEffect, useRef } from 'react';
import { Agent, Tool, updateAgent, getTools, FilterRules } from '../services/api';
import ToolList, { UiTool } from './ToolList';

interface AgentSettingsProps {
  agent: Agent | null;
}

const AgentSettings: React.FC<AgentSettingsProps> = ({ agent }) => {
  const [editableAgent, setEditableAgent] = useState<Agent | null>(agent);
  const [tools, setTools] = useState<UiTool[]>([]);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
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
    if (agent) {
      const agentWithDefaults: Agent = {
        ...agent,
        trigger_conditions: agent.trigger_conditions ?? '',
        filter_rules: agent.filter_rules ?? { email_blacklist: [], email_whitelist: [], domain_blacklist: [], domain_whitelist: [] },
      };
      setEditableAgent(agentWithDefaults);
      setFilterRuleStrings({
        email_blacklist: agent.filter_rules?.email_blacklist.join(', ') || '',
        email_whitelist: agent.filter_rules?.email_whitelist.join(', ') || '',
        domain_blacklist: agent.filter_rules?.domain_blacklist.join(', ') || '',
        domain_whitelist: agent.filter_rules?.domain_whitelist.join(', ') || '',
      });
    } else {
      setEditableAgent(null);
    }

    if (agent) {
      const fetchTools = async () => {
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
      };
      fetchTools();
    }
  }, [agent]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (editableAgent) {
      setEditableAgent({ ...editableAgent, [e.target.name]: e.target.value });
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
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (error) {
      console.error('Error saving agent:', error);
      setSaveStatus('error');
    }
  };

  if (!editableAgent) {
    return <div className="p-8 text-gray-500">Select an agent to view or edit its settings.</div>;
  }

  return (
    <div className="flex-1 p-8 overflow-y-auto">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-start mb-6">
          <h1 className="text-2xl font-bold">{editableAgent.name}</h1>
          <button
            onClick={handleSave}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-blue-300"
            disabled={saveStatus === 'saving'}
          >
            {saveStatus === 'saving' ? 'Saving...' : saveStatus === 'saved' ? 'Saved!' : 'Save Changes'}
          </button>
        </div>
        
        <div className="space-y-8">
          {/* General Settings */}
          <div className="p-4 border rounded-lg bg-gray-50">
            <h2 className="text-xl font-semibold mb-4 border-b pb-2">General</h2>
            <div className="space-y-4 mt-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Name</label>
                <input type="text" name="name" value={editableAgent.name} onChange={handleInputChange} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Description</label>
                <textarea name="description" value={editableAgent.description} onChange={handleInputChange} rows={2} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm" />
              </div>
            </div>
          </div>

          {/* Trigger Settings */}
          <div className="p-4 border rounded-lg bg-gray-50">
            <h2 className="text-xl font-semibold mb-4 border-b pb-2">Trigger Settings</h2>
            <div className="space-y-4 mt-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Trigger Instructions</label>
                <textarea name="trigger_conditions" value={editableAgent.trigger_conditions} onChange={handleInputChange} rows={5} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm" />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700">Email Blacklist (comma-separated)</label>
                  <textarea name="email_blacklist" value={filterRuleStrings.email_blacklist} onChange={handleFilterRuleChange} rows={2} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm" />
                  <p className="text-xs text-gray-600 mt-1">Stop processing emails from these specific addresses. Ex: spam@example.com, junk@mail.net</p>
                  {filterErrors.email_blacklist && <p className="text-xs text-red-600 mt-1">{filterErrors.email_blacklist}</p>}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Email Whitelist (comma-separated)</label>
                  <textarea name="email_whitelist" value={filterRuleStrings.email_whitelist} onChange={handleFilterRuleChange} rows={2} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm" />
                  <p className="text-xs text-gray-600 mt-1">If used, only emails from these addresses will proceed. Ex: boss@mycompany.com</p>
                  {filterErrors.email_whitelist && <p className="text-xs text-red-600 mt-1">{filterErrors.email_whitelist}</p>}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Domain Blacklist (comma-separated)</label>
                  <textarea name="domain_blacklist" value={filterRuleStrings.domain_blacklist} onChange={handleFilterRuleChange} rows={2} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm" />
                  <p className="text-xs text-gray-600 mt-1">Stop processing emails from these domains. Ex: evil-corp.com, bad-actors.org</p>
                  {filterErrors.domain_blacklist && <p className="text-xs text-red-600 mt-1">{filterErrors.domain_blacklist}</p>}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Domain Whitelist (comma-separated)</label>
                  <textarea name="domain_whitelist" value={filterRuleStrings.domain_whitelist} onChange={handleFilterRuleChange} rows={2} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm" />
                  <p className="text-xs text-gray-600 mt-1">If used, only emails from these domains will proceed. Ex: mycompany.com</p>
                  {filterErrors.domain_whitelist && <p className="text-xs text-red-600 mt-1">{filterErrors.domain_whitelist}</p>}
                </div>
              </div>
            </div>
          </div>

          {/* Agent Settings */}
          <div className="p-4 border rounded-lg bg-gray-50">
            <h2 className="text-xl font-semibold mb-4 border-b pb-2">Agent Settings</h2>
            <div className="space-y-4 mt-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">User Instructions</label>
                <textarea name="user_instructions" value={editableAgent.user_instructions} onChange={handleInputChange} rows={5} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm" />
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