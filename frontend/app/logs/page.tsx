'use client';
import React, { useState, useEffect } from 'react';
import ConversationsList from '../../components/ConversationsList';
import ConversationDetail from '../../components/ConversationDetail';
import TopBar from '../../components/TopBar';
import { addReview } from '../../services/api';
import VersionCheck from '../../components/VersionCheck';

type SubmissionStatus = 'idle' | 'sending' | 'success' | 'error';

const LogsPage = () => {
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isFeedbackFormVisible, setIsFeedbackFormVisible] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [submissionStatus, setSubmissionStatus] = useState<SubmissionStatus>('idle');
  const [submissionMessage, setSubmissionMessage] = useState('');

  useEffect(() => {
    if (submissionStatus === 'success' || submissionStatus === 'error') {
      const timer = setTimeout(() => {
        setSubmissionStatus('idle');
        setIsFeedbackFormVisible(false);
        setFeedbackText('');
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [submissionStatus]);

  const handleSelectConversation = (conversationId: string) => {
    setSelectedConversationId(conversationId);
    setIsModalOpen(true);
    // Reset feedback state when opening a new conversation
    setIsFeedbackFormVisible(false);
    setFeedbackText('');
    setSubmissionStatus('idle');
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedConversationId(null);
  };

  const handleSendFeedback = async () => {
    if (!selectedConversationId || !feedbackText) return;
    setSubmissionStatus('sending');
    const result = await addReview(selectedConversationId, feedbackText);
    if (result.success) {
      setSubmissionStatus('success');
      setSubmissionMessage('Feedback submitted successfully!');
    } else {
      setSubmissionStatus('error');
      setSubmissionMessage(result.error || 'Failed to submit feedback.');
    }
  };

  return (
    <div>
      <VersionCheck />
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
                className="absolute top-4 right-4 bg-gray-100 border border-gray-300 rounded py-2 px-3 cursor-pointer text-sm font-bold z-10"
                onClick={handleCloseModal}
              >
                ✕ Close
              </button>
              <ConversationDetail conversationId={selectedConversationId} />

              <div className="sticky bottom-4 right-4 flex justify-end p-4">
                {submissionStatus === 'idle' && !isFeedbackFormVisible && (
                  <div className="text-right bg-white/20 backdrop-blur-lg p-4 rounded-xl shadow-lg border border-white/30">
                    <button
                      onClick={() => setIsFeedbackFormVisible(true)}
                      className="bg-blue-600 text-white font-bold py-2 px-4 rounded-full shadow-lg hover:bg-blue-700 transition"
                    >
                      Send feedback to Arthur
                    </button>
                    <p className="text-xs text-gray-500 mt-1 max-w-xs">
                      This will send this log with your feedback to Arthur. Thanks for making the product better!
                    </p>
                  </div>
                )}

                {isFeedbackFormVisible && submissionStatus === 'idle' && (
                  <div className="flex gap-2 items-center bg-white p-2 rounded-lg shadow-lg">
                    <input
                      type="text"
                      value={feedbackText}
                      onChange={(e) => setFeedbackText(e.target.value)}
                      placeholder="Type your feedback..."
                      className="border rounded px-2 py-1"
                    />
                    <button
                      onClick={handleSendFeedback}
                      disabled={!feedbackText}
                      className="bg-green-500 text-white font-bold py-1 px-3 rounded disabled:bg-gray-400"
                    >
                      Send
                    </button>
                  </div>
                )}
                
                {submissionStatus === 'sending' && <p>Sending...</p>}
                {submissionStatus === 'success' && <p className="text-green-600 bg-green-100 p-2 rounded">{submissionMessage}</p>}
                {submissionStatus === 'error' && <p className="text-red-600 bg-red-100 p-2 rounded">{submissionMessage}</p>}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default LogsPage; 