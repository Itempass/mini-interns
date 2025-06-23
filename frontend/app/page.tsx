'use client';
import React, { useState, useEffect, useRef } from 'react';
import { getAgentSettings, setAgentSettings as apiSetAgentSettings, FilterRules, getMcpServers, McpServer, McpTool } from '../services/api';
import TopBar from '../components/TopBar';

interface AgentSettings {
  systemPrompt: string;
  triggerConditions: string;
  userContext: string;
  filterRules: FilterRules;
  agentSteps: string;
  agentInstructions: string;
}

const Tooltip = ({ content, children }: { content: React.ReactNode, children: React.ReactNode }) => {
  const [isVisible, setIsVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  return (
    <div 
      className="relative inline-block"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <div
          ref={ref}
          className="absolute z-10 w-64 p-2 -mt-1 text-sm text-white bg-gray-800 rounded-lg shadow-lg"
          style={{ bottom: '100%', left: '50%', transform: 'translateX(-50%)', marginBottom: '8px' }}
        >
          {content}
        </div>
      )}
    </div>
  );
};

const HomePage = () => {
  const [agentSettings, setAgentSettings] = useState<AgentSettings>({
    systemPrompt: '',
    triggerConditions: '',
    userContext: '',
    filterRules: {
      email_blacklist: [],
      email_whitelist: [],
      domain_blacklist: [],
      domain_whitelist: [],
    },
    agentSteps: '',
    agentInstructions: '',
  });
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingField, setEditingField] = useState<keyof Omit<AgentSettings, 'filterRules'> | null>(null);
  const [modalContent, setModalContent] = useState('');
  const [filterErrors, setFilterErrors] = useState({
    email_blacklist: '',
    email_whitelist: '',
    domain_blacklist: '',
    domain_whitelist: '',
  });
  const [filterRuleStrings, setFilterRuleStrings] = useState({
    email_blacklist: '',
    email_whitelist: '',
    domain_blacklist: '',
    domain_whitelist: '',
  });
  const [showFilterRules, setShowFilterRules] = useState(false);

  useEffect(() => {
    console.log('Component mounted. Fetching initial data.');
    const fetchInitialData = async () => {
      const fetchedAgentSettings = await getAgentSettings();
      setAgentSettings(prev => ({
        ...prev,
        systemPrompt: fetchedAgentSettings.system_prompt || '',
        triggerConditions: fetchedAgentSettings.trigger_conditions || '',
        userContext: fetchedAgentSettings.user_context || '',
        filterRules: fetchedAgentSettings.filter_rules || {
          email_blacklist: [],
          email_whitelist: [],
          domain_blacklist: [],
          domain_whitelist: [],
        },
        agentSteps: fetchedAgentSettings.agent_steps || '',
        agentInstructions: fetchedAgentSettings.agent_instructions || '',
      }));
      setFilterRuleStrings({
        email_blacklist: fetchedAgentSettings.filter_rules?.email_blacklist.join(', ') || '',
        email_whitelist: fetchedAgentSettings.filter_rules?.email_whitelist.join(', ') || '',
        domain_blacklist: fetchedAgentSettings.filter_rules?.domain_blacklist.join(', ') || '',
        domain_whitelist: fetchedAgentSettings.filter_rules?.domain_whitelist.join(', ') || '',
      });

      const fetchedMcpServers = await getMcpServers();
      setMcpServers(fetchedMcpServers);
    };
    fetchInitialData();
  }, []);

  const handleEdit = (field: keyof Omit<AgentSettings, 'filterRules'>) => {
    setEditingField(field);
    setModalContent(agentSettings[field] as string);
    setIsModalOpen(true);
  };

  const handleModalSave = async () => {
    if (editingField && editingField !== 'triggerConditions') {
      const newSettings = { ...agentSettings, [editingField]: modalContent };
      setAgentSettings(newSettings);
      await apiSetAgentSettings({
        system_prompt: newSettings.systemPrompt,
        user_context: newSettings.userContext,
      });
    }
    setIsModalOpen(false);
  };

  const handleModalClose = () => {
    setIsModalOpen(false);
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

  const handleAgentV2Change = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const { name, value } = e.target as { name: 'agentSteps' | 'agentInstructions' | 'triggerConditions'; value: string };
    setAgentSettings(prev => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleAgentV2Save = async () => {
    await apiSetAgentSettings({
      agent_steps: agentSettings.agentSteps,
      agent_instructions: agentSettings.agentInstructions,
    });
    alert('Execution Agent settings saved!');
  };

  const handleFilterRulesSave = async () => {
    if (Object.values(filterErrors).some(err => err)) {
      alert('Please fix the validation errors before saving.');
      return;
    }
    
    const newFilterRules: FilterRules = {
      email_blacklist: filterRuleStrings.email_blacklist.split(',').map(item => item.trim()).filter(Boolean),
      email_whitelist: filterRuleStrings.email_whitelist.split(',').map(item => item.trim()).filter(Boolean),
      domain_blacklist: filterRuleStrings.domain_blacklist.split(',').map(item => item.trim()).filter(Boolean),
      domain_whitelist: filterRuleStrings.domain_whitelist.split(',').map(item => item.trim()).filter(Boolean),
    };
    
    setAgentSettings(prev => ({ ...prev, filterRules: newFilterRules }));

    await apiSetAgentSettings({
        filter_rules: newFilterRules,
        trigger_conditions: agentSettings.triggerConditions,
    });
    alert('Trigger settings saved!');
  };

  return (
    <div className="flex flex-col h-screen">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <div className="w-full p-10 font-sans overflow-y-auto">
          <div className="max-w-4xl mx-auto">
          <div className="border border-gray-300 p-4 mb-5 rounded-lg bg-gray-50">
              <h2 className="text-center mb-5 text-2xl font-bold">Trigger LLM</h2>
              <p className="text-center text-sm text-gray-600 mb-5">
                The agent is triggered for every new incoming email. Customize trigger settings below.
              </p>

              <div className="mb-3 flex flex-col items-start">
                <button 
                  onClick={() => setShowFilterRules(!showFilterRules)}
                  className="flex items-center gap-2 font-bold px-4 py-2 rounded hover:bg-gray-100 border border-gray-200 shadow-sm transition-colors"
                  type="button"
                >
                  <span>Email blacklist/whitelist rules</span>
                  <svg className={`w-4 h-4 transform transition-transform ${showFilterRules ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                </button>
                {showFilterRules && (
                  <div className="mt-3 w-full pl-4">
                    <div className="mb-3">
                      <label className="block font-semibold mb-1">Email Blacklist:</label>
                      <textarea className="w-full p-2 rounded border border-gray-300 box-border" name="email_blacklist" value={filterRuleStrings.email_blacklist} onChange={handleFilterRuleChange} rows={1} />
                      <p className="text-xs text-gray-600 mt-1">Stop processing emails from these specific addresses. Ex: spam@example.com, junk@mail.net</p>
                      {filterErrors.email_blacklist && <p className="text-xs text-red-600 mt-1">{filterErrors.email_blacklist}</p>}
                    </div>
                    <div className="mb-3">
                      <label className="block font-semibold mb-1">Email Whitelist:</label>
                      <textarea className="w-full p-2 rounded border border-gray-300 box-border" name="email_whitelist" value={filterRuleStrings.email_whitelist} onChange={handleFilterRuleChange} rows={1} />
                      <p className="text-xs text-gray-600 mt-1">If used, only emails from these addresses will proceed to the LLM trigger check. Ex: boss@mycompany.com</p>
                      {filterErrors.email_whitelist && <p className="text-xs text-red-600 mt-1">{filterErrors.email_whitelist}</p>}
                    </div>
                    <div className="mb-3">
                      <label className="block font-semibold mb-1">Domain Blacklist:</label>
                      <textarea className="w-full p-2 rounded border border-gray-300 box-border" name="domain_blacklist" value={filterRuleStrings.domain_blacklist} onChange={handleFilterRuleChange} rows={1} />
                      <p className="text-xs text-gray-600 mt-1">Stop processing emails from these domains. Ex: evil-corp.com, bad-actors.org</p>
                      {filterErrors.domain_blacklist && <p className="text-xs text-red-600 mt-1">{filterErrors.domain_blacklist}</p>}
                    </div>
                    <div className="mb-3">
                      <label className="block font-semibold mb-1">Domain Whitelist:</label>
                      <textarea className="w-full p-2 rounded border border-gray-300 box-border" name="domain_whitelist" value={filterRuleStrings.domain_whitelist} onChange={handleFilterRuleChange} rows={1} />
                      <p className="text-xs text-gray-600 mt-1">If used, only emails from these domains will proceed to the LLM trigger check. Ex: mycompany.com, important-client.com</p>
                      {filterErrors.domain_whitelist && <p className="text-xs text-red-600 mt-1">{filterErrors.domain_whitelist}</p>}
                    </div>
                  </div>
                )}
              </div>

              <div className="flex items-start mb-3">
                <label className="mr-2 w-48 text-right font-bold pt-2">Trigger Instructions:</label>
                <div className="flex-1">
                  <textarea 
                    className="w-full p-2 rounded border border-gray-300 box-border" 
                    name="triggerConditions" 
                    value={agentSettings.triggerConditions} 
                    onChange={handleAgentV2Change}
                    rows={6}
                  />
                  <p className="text-xs text-gray-600 mt-1">Provide detailed instructions for the Trigger LLM. It will use these to decide whether to start the Execution Agent.</p>
                  <p className="text-xs text-gray-500 mt-1">You can use <code>{'<<CURRENT_DATE>>'}</code> which will be replaced with the current date (YYYY-MM-DD).</p>
                </div>
              </div>

              <button className="py-2 px-5 border-none rounded bg-blue-500 text-white cursor-pointer text-base block mx-auto" onClick={handleFilterRulesSave}>Save Trigger Settings</button>
            </div>



            
            <div className="border border-gray-300 p-4 mb-5 rounded-lg bg-gray-50">
              
              <h2 className="text-center mb-5 text-2xl font-bold">Execution Agent</h2>
              <p className="text-center -mt-4 mb-5 text-gray-600">
                Set up your agent here.
              </p>
              
              {/*<div className="flex items-start mb-3">
                <label className="mr-2 w-48 text-right font-bold pt-2">Agent Steps:</label>
                <div className="flex-1">
                  <textarea 
                    className="w-full p-2 rounded border border-gray-300 box-border" 
                    name="agentSteps" 
                    value={agentSettings.agentSteps} 
                    onChange={handleAgentV2Change}
                    rows={3}
                  />
                  <p className="text-xs text-gray-600 mt-1">Define the steps for the agent.</p>
                  <p className="text-xs text-gray-500 mt-1">You can use <code>{'<<CURRENT_DATE>>'}</code> which will be replaced with the current date (YYYY-MM-DD).</p>
                </div>
              </div>*/}

              <div className="flex items-start mb-3">
                <label className="mr-2 w-48 text-right font-bold pt-2">Agent Instructions:</label>
                <div className="flex-1">
                  <textarea
                    className="w-full p-2 rounded border border-gray-300 box-border"
                    name="agentInstructions"
                    value={agentSettings.agentInstructions}
                    onChange={handleAgentV2Change}
                    rows={6}
                  />
                  <p className="text-xs text-gray-600 mt-1">Provide detailed instructions for the agent.</p>
                  <p className="text-xs text-gray-500 mt-1">You can use <code>{'<<CURRENT_DATE>>'}</code> which will be replaced with the current date (YYYY-MM-DD).</p>
                </div>
              </div>

              <div className="flex items-start mb-3">
                <label className="mr-2 w-48 text-right font-bold pt-2">Tools:</label>
                <div className="flex-1 flex flex-wrap gap-2 pt-2">
                  {mcpServers.map(server =>
                    server.tools.map(tool => (
                      <Tooltip 
                        key={`${server.name}-${tool.name}`}
                        content={
                          <div>
                            <p className="font-bold">{tool.name}</p>
                            <p className="text-xs">{tool.description}</p>
                            {Object.keys(tool.inputSchema).length > 0 && (
                              <div className="mt-2 pt-1 border-t border-gray-600">
                                <p className="font-semibold text-xs">Inputs:</p>
                                <ul className="list-disc list-inside text-xs">
                                  {Object.entries(tool.inputSchema).map(([key, value]) => (
                                    <li key={key}>
                                      <code>{key}</code>: {(value as any).description || (value as any).type || ''}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        }
                      >
                        <span className="bg-gray-200 text-gray-800 text-sm font-medium px-2 py-1 rounded-md cursor-default">
                          {server.name.toUpperCase()}: {tool.name}
                        </span>
                      </Tooltip>
                    ))
                  )}
                </div>
              </div>
              <button className="py-2 px-5 border-none rounded bg-blue-500 text-white cursor-pointer text-base block mx-auto" onClick={handleAgentV2Save}>Save Execution Agent Settings</button>
            </div>

            

            
          </div>
        </div>
      </div>

      {isModalOpen && (
        <div className="fixed top-0 left-0 right-0 bottom-0 bg-black bg-opacity-50 flex justify-center items-center z-50">
          <div className="bg-white p-5 rounded-lg w-[800px] max-h-[80vh] flex flex-col shadow-lg">
            <h3 className="mt-0 text-xl font-bold mb-4">Edit {editingField && (editingField.charAt(0).toUpperCase() + editingField.slice(1)).replace(/([A-Z])/g, ' $1').trim()}</h3>
            <textarea
              className="w-full min-h-[400px] mb-2 p-2 rounded border border-gray-300 box-border resize-y"
              value={modalContent}
              onChange={(e) => setModalContent(e.target.value)}
            />
            <p className="text-xs text-gray-500 -mt-1 mb-2">You can use <code>{'<<CURRENT_DATE>>'}</code> which will be replaced with the current date (YYYY-MM-DD).</p>
            <div className="flex justify-end">
              <button className="py-2 px-5 mr-2 border-none rounded bg-blue-500 text-white cursor-pointer" onClick={handleModalSave}>Save</button>
              <button className="py-2 px-5 border-none rounded bg-gray-500 text-white cursor-pointer" onClick={handleModalClose}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default HomePage; 