'use client';
import React, { useState, useEffect } from 'react';
import TopBar from '../components/TopBar';
import AgentSidebar from '../components/AgentSidebar';
import AgentSettings from '../components/AgentSettings';
import AgentSettingsAbstracted from '../components/AgentSettingsAbstracted';
import { Agent, getAgents } from '../services/api';
import VersionCheck from '../components/VersionCheck';
import ConnectionStatusIndicator from '../components/ConnectionStatusIndicator';
import NoAgentsView from '../components/NoAgentsView';

const HomePage = () => {
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);

  const fetchAgents = async () => {
    const freshAgents = await getAgents();
    setAgents(freshAgents);

    if (selectedAgent) {
      const updatedSelectedAgent = freshAgents.find(agent => agent.uuid === selectedAgent.uuid);
      setSelectedAgent(updatedSelectedAgent || (freshAgents.length > 0 ? freshAgents[0] : null));
    } else if (freshAgents.length > 0) {
      setSelectedAgent(freshAgents[0]);
    } else {
      setSelectedAgent(null);
    }
  };

  useEffect(() => {
    fetchAgents();
  }, []);

  const handleSelectAgent = (agent: Agent | null) => {
    setSelectedAgent(agent);
  };

  return (
    <div className="flex flex-col h-screen bg-white">
      <VersionCheck />
      <div className="flex flex-col flex-grow overflow-hidden">
        <TopBar />
        <div className="flex flex-1 overflow-hidden">
          <div className="w-64 flex-shrink-0 flex flex-col bg-gray-50 border-r border-gray-200">
            <div className="flex flex-col flex-grow overflow-y-auto">
              <AgentSidebar 
                agents={agents}
                onSelectAgent={handleSelectAgent} 
                selectedAgent={selectedAgent} 
                onAgentsUpdate={fetchAgents}
              />
            </div>
            <ConnectionStatusIndicator />
          </div>
          <main className="flex-1 overflow-y-auto bg-gray-100">
            {agents.length > 0 && selectedAgent ? (
              selectedAgent.use_abstracted_editor ? (
                <AgentSettingsAbstracted key={selectedAgent.uuid} agent={selectedAgent} onAgentUpdate={fetchAgents} />
              ) : (
                <AgentSettings key={selectedAgent.uuid} agent={selectedAgent} onAgentUpdate={fetchAgents} />
              )
            ) : (
              <NoAgentsView />
            )}
          </main>
        </div>
      </div>
    </div>
  );
};

export default HomePage; 