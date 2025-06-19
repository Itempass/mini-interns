'use client';
import React, { useState } from 'react';
import ConversationsList from '../../components/ConversationsList';
import ConversationDetail from '../../components/ConversationDetail';

const LogsPage = () => {
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleSelectConversation = (conversationId: string) => {
    setSelectedConversationId(conversationId);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedConversationId(null);
  };

  const containerStyle: React.CSSProperties = {
    padding: '40px',
    maxWidth: '1200px',
    margin: '0 auto',
    fontFamily: 'Arial, sans-serif',
  };

  const modalOverlayStyle: React.CSSProperties = {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1000,
  };

  const modalContentStyle: React.CSSProperties = {
    backgroundColor: 'white',
    borderRadius: '8px',
    width: '90%',
    maxWidth: '1000px',
    maxHeight: '90vh',
    overflow: 'auto',
    boxShadow: '0 4px 8px rgba(0,0,0,0.1)',
    position: 'relative',
  };

  const closeButtonStyle: React.CSSProperties = {
    position: 'absolute',
    top: '16px',
    right: '16px',
    background: '#f0f0f0',
    border: '1px solid #ccc',
    borderRadius: '4px',
    padding: '8px 12px',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: 'bold',
  };

  const titleStyle: React.CSSProperties = {
    textAlign: 'center',
    marginBottom: '20px',
    color: '#333',
  };

  return (
    <div style={containerStyle}>
      <h1 style={titleStyle}>Agent Logger - Conversation Logs</h1>
      
      <ConversationsList onSelectConversation={handleSelectConversation} />

      {isModalOpen && selectedConversationId && (
        <div style={modalOverlayStyle} onClick={handleCloseModal}>
          <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>
            <button style={closeButtonStyle} onClick={handleCloseModal}>
              ✕ Close
            </button>
            <ConversationDetail conversationId={selectedConversationId} />
          </div>
        </div>
      )}
    </div>
  );
};

export default LogsPage; 