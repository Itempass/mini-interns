'use client';
import React, { useState, useEffect } from 'react';
import { getConversations, ConversationData } from '../services/api';

interface ToolCall {
  id: string;
  function: {
    name: string;
  };
}

interface Message {
  role: 'assistant' | 'user' | 'system' | 'tool';
  tool_calls?: ToolCall[];
}

const getToolChain = (messages: Message[]): { id: string; name: string }[] => {
  const toolChain: { id: string; name: string }[] = [];
  messages.forEach((message) => {
    if (message.role === 'assistant' && message.tool_calls) {
      message.tool_calls.forEach((toolCall) => {
        toolChain.push({ id: toolCall.id, name: toolCall.function.name });
      });
    }
  });
  return toolChain;
};

interface ConversationsListProps {
  onSelectConversation?: (conversationId: string) => void;
}

const ConversationsList: React.FC<ConversationsListProps> = ({ onSelectConversation }) => {
  const [conversations, setConversations] = useState<ConversationData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchConversations = async () => {
      setLoading(true);
      const response = await getConversations();
      setConversations(response.conversations);
      setLoading(false);
    };
    fetchConversations();
  }, []);

  const handleRowClick = (conversationId: string) => {
    if (onSelectConversation) {
      onSelectConversation(conversationId);
    }
  };

  const handleDownload = () => {
    if (conversations.length === 0) {
      return;
    }
    const jsonString = JSON.stringify(conversations, null, 2);
    const blob = new Blob([jsonString], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "conversations.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return <div>Loading conversations...</div>;
  }

  const thClasses = "p-3 text-left font-bold text-white bg-blue-500 border border-gray-300";
  const tdClasses = "p-3 bg-white border border-gray-300";
  const conversationIdTdClasses = `${tdClasses} max-w-[20ch] overflow-hidden text-ellipsis whitespace-nowrap`;
  const contextTdClasses = `${tdClasses} max-w-[30ch]`;

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="m-0">Agent Logger Conversations ({conversations.length})</h2>
        <button
          onClick={handleDownload}
          disabled={conversations.length === 0}
          className="px-4 py-2 text-white bg-blue-500 border-none rounded-md cursor-pointer disabled:bg-gray-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Download as JSON
        </button>
      </div>
      <table className="w-full bg-gray-50 border border-gray-300 border-collapse">
        <thead>
          <tr>
            <th className={thClasses}>Conversation ID</th>
            <th className={thClasses}>Workflow Name</th>
            <th className={thClasses}>Context</th>
            <th className={thClasses}>Messages</th>
            <th className={thClasses}>Timestamp</th>
            <th className={thClasses}>Tool Chain</th>
          </tr>
        </thead>
        <tbody>
          {conversations.map((conversation) => (
            <tr
              key={conversation.metadata.conversation_id}
              className={onSelectConversation ? 'cursor-pointer hover:bg-gray-100' : 'cursor-default'}
              onClick={() => handleRowClick(conversation.metadata.conversation_id)}
            >
              <td className={conversationIdTdClasses} title={conversation.metadata.conversation_id}>
                {conversation.metadata.conversation_id}
              </td>
              <td className={tdClasses}>{conversation.metadata.readable_workflow_name || 'N/A'}</td>
              <td className={contextTdClasses} title={conversation.metadata.readable_instance_context || ''}>
                <span className="line-clamp-3">
                  {conversation.metadata.readable_instance_context || 'N/A'}
                </span>
              </td>
              <td className={tdClasses}>{conversation.messages.length}</td>
              <td className={tdClasses}>
                {conversation.metadata.timestamp 
                  ? new Date(conversation.metadata.timestamp).toLocaleString() 
                  : 'N/A'}
              </td>
              <td className={tdClasses}>
                <div className="flex flex-wrap items-center">
                  {getToolChain(conversation.messages as Message[]).map((tool, index, arr) => (
                    <div key={tool.id} className="flex items-center mb-1 mr-1">
                      <span
                        className="px-2 py-0.5 text-sm font-medium text-blue-800 bg-blue-100 rounded-full"
                        title={`Tool: ${tool.name}`}
                      >
                        {tool.name}
                      </span>
                      {index < arr.length - 1 && (
                        <span className="mx-1.5 text-gray-400">→</span>
                      )}
                    </div>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {conversations.length === 0 && (
        <p className="p-5 text-center">No conversations found.</p>
      )}
    </div>
  );
};

export default ConversationsList; 