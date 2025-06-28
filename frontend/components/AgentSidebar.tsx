'use client';
import React, { useState } from 'react';
import { Agent, createAgent, deleteAgent } from '../services/api';
import { MoreVertical, Trash2 } from 'lucide-react';

interface AgentSidebarProps {
  agents: Agent[];
  onSelectAgent: (agent: Agent | null) => void;
  selectedAgent: Agent | null;
  onAgentsUpdate: () => void;
}

const AgentSidebar: React.FC<AgentSidebarProps> = ({ agents, onSelectAgent, selectedAgent, onAgentsUpdate }) => {
  const [error, setError] = useState<string | null>(null);
  const [menuOpenFor, setMenuOpenFor] = useState<string | null>(null);

  const handleCreateAgent = async () => {
    const newAgentName = `New Agent ${agents.length + 1}`;
    const newAgent = await createAgent({
      name: newAgentName,
      description: "A newly created agent."
    });
    if (newAgent) {
      onAgentsUpdate();
      onSelectAgent(newAgent);
    } else {
      setError('Failed to create agent.');
    }
  };

  const handleDeleteAgent = async (uuid: string) => {
    if (window.confirm('Are you sure you want to delete this agent?')) {
      try {
        await deleteAgent(uuid);
        setMenuOpenFor(null);
        onAgentsUpdate();
      } catch (e) {
        setError('Failed to delete agent.');
        console.error(e);
      }
    }
  };

  return (
    <div className="w-64 bg-gray-50 h-full p-4 border-r border-gray-200 flex flex-col">
      <h2 className="text-lg font-bold mb-4">Agents</h2>
      {error && <p className="text-red-500 text-sm mb-2">{error}</p>}
      <ul className="flex-grow">
        {agents.map((agent) => (
          <li key={agent.uuid} className="mb-2 relative">
            <div className="flex items-center justify-between">
              <button
                onClick={() => onSelectAgent(agent)}
                className={`flex w-full items-center justify-between text-left px-3 py-2 rounded-md text-sm transition-colors ${
                  selectedAgent?.uuid === agent.uuid
                    ? 'bg-blue-500 text-white'
                    : 'bg-white hover:bg-gray-100'
                }`}
              >
                <span>{agent.name}</span>
                {!agent.paused ? (
                    <span className="ml-2 rounded-full bg-green-100 px-2 py-1 text-xs font-bold text-green-800">
                        ON
                    </span>
                ) : (
                    <span className="ml-2 rounded-full bg-red-100 px-2 py-1 text-xs font-bold text-red-800">
                        OFF
                    </span>
                )}
              </button>
              <button
                onClick={() => setMenuOpenFor(menuOpenFor === agent.uuid ? null : agent.uuid)}
                className="p-1 rounded-md hover:bg-gray-200 ml-1"
                aria-label="Agent options"
              >
                <MoreVertical size={16} />
              </button>
            </div>
            {menuOpenFor === agent.uuid && (
              <div className="absolute right-0 mt-1 w-32 bg-white border rounded-md shadow-lg z-10">
                <button
                  onClick={() => handleDeleteAgent(agent.uuid)}
                  className="flex items-center w-full px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                >
                  <Trash2 size={14} className="mr-2" />
                  Delete
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <button 
        onClick={handleCreateAgent}
        className="w-full mt-4 bg-green-500 text-white py-2 rounded-md hover:bg-green-600"
      >
        + New Agent
      </button>
    </div>
  );
};

export default AgentSidebar; 