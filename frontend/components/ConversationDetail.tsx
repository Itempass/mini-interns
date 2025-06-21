'use client';
import React, { useState, useEffect } from 'react';
import { getConversation, ConversationData } from '../services/api';

interface ToolCall {
  id: string;
  type: string;
  function: {
    name: string;
    arguments: string;
  };
}

interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | null;
  name?: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}

const roleToColorMap: { [key: string]: string } = {
  system: 'bg-gray-200 text-gray-800',
  user: 'bg-blue-100 text-blue-900',
  assistant: 'bg-green-100 text-green-900',
  tool: 'bg-yellow-100 text-yellow-900',
};

const formatToolArguments = (args: string) => {
  try {
    const parsed = JSON.parse(args);
    return JSON.stringify(parsed, null, 2);
  } catch (e) {
    return args;
  }
};

interface ConversationDetailProps {
  conversationId: string;
}

const ConversationDetail: React.FC<ConversationDetailProps> = ({ conversationId }) => {
  const [conversation, setConversation] = useState<ConversationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchConversation = async () => {
      setLoading(true);
      setError(null);
      const data = await getConversation(conversationId);
      if (data) {
        setConversation(data);
      } else {
        setError('Conversation not found');
      }
      setLoading(false);
    };
    fetchConversation();
  }, [conversationId]);

  if (loading) {
    return <div className="p-5 max-w-6xl mx-auto font-sans">Loading conversation...</div>;
  }

  if (error) {
    return <div className="p-5 max-w-6xl mx-auto font-sans">Error: {error}</div>;
  }

  if (!conversation) {
    return <div className="p-5 max-w-6xl mx-auto font-sans">Conversation not found</div>;
  }

  return (
    <div className="p-5 max-w-6xl mx-auto font-sans">
      <h2 className="mb-5 text-2xl font-bold">Conversation Detail</h2>
      
      {/* Metadata Section */}
      <div className="p-4 mb-5 bg-gray-50 border border-gray-300 rounded-lg">
        <h3 className="mt-0 mb-4 text-xl font-semibold">Metadata</h3>
        <div className="flex mb-2">
          <span className="font-bold w-[150px] mr-2">ID:</span>
          <span>{conversation.metadata.conversation_id}</span>
        </div>
        <div className="flex mb-2">
          <span className="font-bold w-[150px] mr-2">Service:</span>
          <span>{conversation.metadata.service || 'N/A'}</span>
        </div>
        <div className="flex mb-2">
          <span className="font-bold w-[150px] mr-2">Workflow Type:</span>
          <span>{conversation.metadata.workflow_type || 'N/A'}</span>
        </div>
        <div className="flex mb-2">
          <span className="font-bold w-[150px] mr-2">Email Subject:</span>
          <span>{conversation.metadata.email_subject || 'N/A'}</span>
        </div>
        <div className="flex mb-2">
          <span className="font-bold w-[150px] mr-2">Messages Count:</span>
          <span>{conversation.messages.length}</span>
        </div>
        <div className="flex mb-2">
          <span className="font-bold w-[150px] mr-2">Timestamp:</span>
          <span>
            {conversation.metadata.timestamp ? new Date(conversation.metadata.timestamp).toLocaleString() : 'N/A'}
          </span>
        </div>
        {/* Show any additional metadata fields */}
        {Object.entries(conversation.metadata)
          .filter(([key]) => !['conversation_id', 'service', 'workflow_type', 'email_subject', 'timestamp'].includes(key))
          .map(([key, value]) => (
            <div key={key} className="flex mb-2">
              <span className="font-bold w-[150px] mr-2">{key}:</span>
              <span>{String(value)}</span>
            </div>
          ))}
      </div>

      {/* Messages Section */}
      <div className="mt-8">
        <h3 className="text-xl font-semibold mb-4">Messages</h3>
        <div className="space-y-6">
          {(conversation.messages as Message[]).map((message, index) => (
            <div key={index} className="p-5 border rounded-lg bg-white shadow-sm">
              <div className="flex justify-between items-center mb-4">
                <span className={`font-semibold px-3 py-1 rounded-md text-sm ${roleToColorMap[message.role] || 'bg-gray-100'}`}>
                  {message.role === 'tool' ? `tool: ${message.name}` : message.role}
                </span>
              </div>
              {message.content && (
                message.role === 'tool' 
                ? <pre className="mt-4 font-mono text-sm p-3 bg-yellow-50 rounded whitespace-pre-wrap">{message.content}</pre>
                : <p className="text-gray-800 whitespace-pre-wrap leading-relaxed">{message.content}</p>
              )}
              {message.tool_calls && (
                <div className="mt-4">
                  <h3 className="text-md font-semibold text-gray-800 mb-2">Tool Calls</h3>
                  {message.tool_calls.map((toolCall, i) => (
                    <div key={i} className="mt-2 p-3 bg-gray-50 rounded font-mono text-sm">
                      <div className="text-gray-700"><strong>ID:</strong> {toolCall.id}</div>
                      <div className="text-gray-700"><strong>Type:</strong> {toolCall.type}</div>
                      <div className="text-gray-700"><strong>Function:</strong> {toolCall.function.name}</div>
                      <div className="text-gray-700">
                        <strong>Arguments:</strong>
                        <pre className="whitespace-pre-wrap bg-gray-100 p-2 rounded mt-1">
                          {formatToolArguments(toolCall.function.arguments)}
                        </pre>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {message.role === 'tool' && message.tool_call_id && (
                <div className="mt-4 font-mono text-sm p-3 bg-yellow-50 rounded">
                  <div className="text-gray-700"><strong>Tool Call ID:</strong> {message.tool_call_id}</div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* JSON Section */}
      <div className="p-4 mt-8 bg-gray-50 border border-gray-300 rounded-lg">
        <h3 className="mt-0 mb-4 text-xl font-semibold">Full Conversation Data (JSON)</h3>
        <pre className="p-4 overflow-x-auto text-sm bg-white border border-gray-200 rounded max-h-[600px] overflow-y-auto font-mono">
          {JSON.stringify(conversation, null, 2)}
        </pre>
      </div>
    </div>
  );
};

export default ConversationDetail; 