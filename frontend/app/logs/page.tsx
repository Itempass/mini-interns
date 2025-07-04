'use client';
import React, { useState, useEffect } from 'react';
import ConversationsList from '../../components/ConversationsList';
import ConversationDetail from '../../components/ConversationDetail';
import TopBar from '../../components/TopBar';
import { addReview, getConversation, ConversationData } from '../../services/api';
import VersionCheck from '../../components/VersionCheck';

type SubmissionStatus = 'idle' | 'sending' | 'success' | 'error';

const LogsPage = () => {
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [selectedConversation, setSelectedConversation] = useState<ConversationData | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isFeedbackFormVisible, setIsFeedbackFormVisible] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [submissionStatus, setSubmissionStatus] = useState<SubmissionStatus>('idle');
  const [submissionMessage, setSubmissionMessage] = useState('');
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);

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

  const handleSelectConversation = async (conversationId: string) => {
    setSelectedConversationId(conversationId);
    setIsModalOpen(true);
    // Reset feedback state when opening a new conversation
    setIsFeedbackFormVisible(false);
    setFeedbackText('');
    setSubmissionStatus('idle');

    setIsLoadingConversation(true);
    const data = await getConversation(conversationId);
    if (data) {
      setSelectedConversation(data);
    } else {
      console.error("Could not load conversation");
      // Optionally handle error in UI
    }
    setIsLoadingConversation(false);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedConversationId(null);
    setSelectedConversation(null);
  };

  const handleSendFeedback = async () => {
    if (!selectedConversationId || !feedbackText || !selectedConversation) return;
    setSubmissionStatus('sending');
    const result = await addReview(selectedConversationId, feedbackText, selectedConversation);
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

        {isModalOpen && (
          <div className="fixed inset-0 z-50 overflow-y-auto bg-gray-900 bg-opacity-75 flex justify-center items-center">
            <div className="bg-white rounded-lg shadow-2xl w-full max-w-4xl h-[90vh] flex flex-col relative">
              <div className="flex justify-between items-center p-4 border-b">
                <h2 className="text-xl font-bold">Conversation Details</h2>
                <button onClick={handleCloseModal} className="text-gray-500 hover:text-gray-800 text-3xl font-bold">&times;</button>
              </div>

              <div className="p-5 overflow-y-auto flex-grow">
                {isLoadingConversation ? (
                  <div>Loading...</div>
                ) : selectedConversation ? (
                  <ConversationDetail conversation={selectedConversation} />
                ) : (
                  <div>Conversation not found.</div>
                )}
              </div>

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