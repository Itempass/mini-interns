'use client';
import React, { useState } from 'react';
import ConversationsList from '../../components/ConversationsList';
import ConversationDetail from '../../components/ConversationDetail';
import TopBar from '../../components/TopBar';

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

  return (
    <div>
      <TopBar />
      <div className="p-10 max-w-7xl mx-auto font-sans">
        <h1 className="text-center mb-5 text-2xl font-bold text-gray-800">Agent Logger - Conversation Logs</h1>
        
        <ConversationsList onSelectConversation={handleSelectConversation} />

        {isModalOpen && selectedConversationId && (
          <div 
            className="fixed top-0 left-0 right-0 bottom-0 bg-black bg-opacity-50 flex justify-center items-center z-50"
            onClick={handleCloseModal}
          >
            <div 
              className="bg-white rounded-lg w-11/12 max-w-5xl max-h-[90vh] overflow-auto shadow-lg relative"
              onClick={(e) => e.stopPropagation()}
            >
              <button 
                className="absolute top-4 right-4 bg-gray-100 border border-gray-300 rounded py-2 px-3 cursor-pointer text-sm font-bold"
                onClick={handleCloseModal}
              >
                ✕ Close
              </button>
              <ConversationDetail conversationId={selectedConversationId} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default LogsPage; 