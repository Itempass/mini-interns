'use client';
import React, { useState } from 'react';
import TopBar from '../components/TopBar';
import AgentSidebar from '../components/AgentSidebar';
import AgentSettings from '../components/AgentSettings';
import { Agent } from '../services/api';

const HomePage = () => {
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);

  const handleSelectAgent = (agent: Agent | null) => {
    setSelectedAgent(agent);
  };

  return (
    <div className="flex flex-col h-screen">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <AgentSidebar onSelectAgent={handleSelectAgent} selectedAgent={selectedAgent} />
        <main className="flex-1 overflow-y-auto bg-gray-100">
          <AgentSettings agent={selectedAgent} />
        </main>
      </div>
    </div>
  );
};

export default HomePage; 