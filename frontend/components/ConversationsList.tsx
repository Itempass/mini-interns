'use client';
import React, { useState, useEffect } from 'react';
import { getConversations, ConversationData } from '../services/api';

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

  const tableStyle: React.CSSProperties = {
    width: '100%',
    borderCollapse: 'collapse',
    border: '1px solid #ccc',
    backgroundColor: '#f9f9f9',
  };

  const thStyle: React.CSSProperties = {
    border: '1px solid #ccc',
    padding: '12px',
    backgroundColor: '#007bff',
    color: 'white',
    textAlign: 'left',
    fontWeight: 'bold',
  };

  const tdStyle: React.CSSProperties = {
    border: '1px solid #ccc',
    padding: '12px',
    backgroundColor: 'white',
  };

  const rowStyle: React.CSSProperties = {
    cursor: onSelectConversation ? 'pointer' : 'default',
  };

  const handleRowClick = (conversationId: string) => {
    if (onSelectConversation) {
      onSelectConversation(conversationId);
    }
  };

  if (loading) {
    return <div>Loading conversations...</div>;
  }

  return (
    <div>
      <h2 style={{ marginBottom: '20px' }}>Agent Logger Conversations ({conversations.length})</h2>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>Conversation ID</th>
            <th style={thStyle}>Service</th>
            <th style={thStyle}>Workflow Type</th>
            <th style={thStyle}>Email Subject</th>
            <th style={thStyle}>Messages</th>
            <th style={thStyle}>Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {conversations.map((conversation) => (
            <tr
              key={conversation.metadata.conversation_id}
              style={rowStyle}
              onClick={() => handleRowClick(conversation.metadata.conversation_id)}
            >
              <td style={tdStyle}>{conversation.metadata.conversation_id}</td>
              <td style={tdStyle}>{conversation.metadata.service || 'N/A'}</td>
              <td style={tdStyle}>{conversation.metadata.workflow_type || 'N/A'}</td>
              <td style={tdStyle}>{conversation.metadata.email_subject || 'N/A'}</td>
              <td style={tdStyle}>{conversation.messages.length}</td>
              <td style={tdStyle}>
                {conversation.metadata.timestamp 
                  ? new Date(conversation.metadata.timestamp).toLocaleString() 
                  : 'N/A'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {conversations.length === 0 && (
        <p style={{ textAlign: 'center', padding: '20px' }}>No conversations found.</p>
      )}
    </div>
  );
};

export default ConversationsList; 