'use client';
import React, { useState, useEffect } from 'react';
import { getConversation, ConversationData } from '../services/api';

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

  const containerStyle: React.CSSProperties = {
    padding: '20px',
    maxWidth: '1200px',
    margin: '0 auto',
    fontFamily: 'Arial, sans-serif',
  };

  const metadataSectionStyle: React.CSSProperties = {
    border: '1px solid #ccc',
    padding: '16px',
    marginBottom: '20px',
    borderRadius: '8px',
    backgroundColor: '#f9f9f9',
  };

  const metadataRowStyle: React.CSSProperties = {
    display: 'flex',
    marginBottom: '8px',
  };

  const labelStyle: React.CSSProperties = {
    fontWeight: 'bold',
    width: '150px',
    marginRight: '10px',
  };

  const jsonSectionStyle: React.CSSProperties = {
    border: '1px solid #ccc',
    padding: '16px',
    borderRadius: '8px',
    backgroundColor: '#f9f9f9',
  };

  const preStyle: React.CSSProperties = {
    backgroundColor: 'white',
    border: '1px solid #ddd',
    borderRadius: '4px',
    padding: '16px',
    overflowX: 'auto',
    fontSize: '14px',
    fontFamily: 'monospace',
    maxHeight: '600px',
    overflowY: 'auto',
  };

  if (loading) {
    return <div style={containerStyle}>Loading conversation...</div>;
  }

  if (error) {
    return <div style={containerStyle}>Error: {error}</div>;
  }

  if (!conversation) {
    return <div style={containerStyle}>Conversation not found</div>;
  }

  return (
    <div style={containerStyle}>
      <h2 style={{ marginBottom: '20px' }}>Conversation Detail</h2>
      
      {/* Metadata Section */}
      <div style={metadataSectionStyle}>
        <h3 style={{ marginTop: 0, marginBottom: '16px' }}>Metadata</h3>
        <div style={metadataRowStyle}>
          <span style={labelStyle}>ID:</span>
          <span>{conversation.metadata.conversation_id}</span>
        </div>
        <div style={metadataRowStyle}>
          <span style={labelStyle}>Service:</span>
          <span>{conversation.metadata.service || 'N/A'}</span>
        </div>
        <div style={metadataRowStyle}>
          <span style={labelStyle}>Workflow Type:</span>
          <span>{conversation.metadata.workflow_type || 'N/A'}</span>
        </div>
        <div style={metadataRowStyle}>
          <span style={labelStyle}>Email Subject:</span>
          <span>{conversation.metadata.email_subject || 'N/A'}</span>
        </div>
        <div style={metadataRowStyle}>
          <span style={labelStyle}>Messages Count:</span>
          <span>{conversation.messages.length}</span>
        </div>
        <div style={metadataRowStyle}>
          <span style={labelStyle}>Timestamp:</span>
          <span>
            {conversation.metadata.timestamp 
              ? new Date(conversation.metadata.timestamp).toLocaleString() 
              : 'N/A'}
          </span>
        </div>
        {/* Show any additional metadata fields */}
        {Object.entries(conversation.metadata)
          .filter(([key]) => !['conversation_id', 'service', 'workflow_type', 'email_subject', 'timestamp'].includes(key))
          .map(([key, value]) => (
            <div key={key} style={metadataRowStyle}>
              <span style={labelStyle}>{key}:</span>
              <span>{String(value)}</span>
            </div>
          ))}
      </div>

      {/* JSON Section */}
      <div style={jsonSectionStyle}>
        <h3 style={{ marginTop: 0, marginBottom: '16px' }}>Full Conversation Data (JSON)</h3>
        <pre style={preStyle}>
          {JSON.stringify(conversation, null, 2)}
        </pre>
      </div>
    </div>
  );
};

export default ConversationDetail; 