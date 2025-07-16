'use client';
import React, { useState, useEffect } from 'react';
import LogsList from '../../components/LogsList';
import LogDetail from '../../components/LogDetail';
import TopBar from '../../components/TopBar';
import { addReview, getLogEntry, LogEntry } from '../../services/api';
import VersionCheck from '../../components/VersionCheck';

type SubmissionStatus = 'idle' | 'sending' | 'success' | 'error';

const LogsPage = () => {
  const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isFeedbackFormVisible, setIsFeedbackFormVisible] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [needsReview, setNeedsReview] = useState(true);
  const [submissionStatus, setSubmissionStatus] = useState<SubmissionStatus>('idle');
  const [submissionMessage, setSubmissionMessage] = useState('');
  const [isLoadingLog, setIsLoadingLog] = useState(false);

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

  const handleSelectLog = async (logId: string) => {
    setSelectedLogId(logId);
    setIsModalOpen(true);
    setIsFeedbackFormVisible(false);
    setFeedbackText('');
    setSubmissionStatus('idle');

    setIsLoadingLog(true);
    const data = await getLogEntry(logId);
    if (data) {
      setSelectedLog(data);
      setNeedsReview(data.needs_review ?? true);
    } else {
      console.error("Could not load log");
    }
    setIsLoadingLog(false);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedLogId(null);
    setSelectedLog(null);
  };

  const handleSendFeedback = async () => {
    if (!selectedLogId || !feedbackText || !selectedLog) return;
    setSubmissionStatus('sending');
    const result = await addReview(selectedLogId, feedbackText, needsReview, selectedLog);
    if (result.success) {
      setSubmissionStatus('success');
      setSubmissionMessage('Feedback submitted successfully!');
      // Optionally, refresh the log list or update the specific log entry in the state
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
        <h1 className="text-center mb-5 text-2xl font-bold text-gray-800">Agent Logs</h1>
        
        <LogsList onSelectLog={handleSelectLog} />

        {isModalOpen && (
          <div className="fixed inset-0 z-50 overflow-y-auto bg-gray-900 bg-opacity-75 flex justify-center items-center">
            <div className="bg-white rounded-lg shadow-2xl w-full max-w-6xl h-[90vh] flex flex-col relative">
              <div className="flex justify-between items-center p-4 border-b">
                <h2 className="text-xl font-bold">Log Details</h2>
                <button onClick={handleCloseModal} className="text-gray-500 hover:text-gray-800 text-3xl font-bold">&times;</button>
              </div>

              <div className="p-5 overflow-y-auto flex-grow">
                {isLoadingLog ? (
                  <div>Loading...</div>
                ) : selectedLog ? (
                  <LogDetail log={selectedLog} />
                ) : (
                  <div>Log not found.</div>
                )}
              </div>

              <div className="flex justify-end p-4 border-t bg-gray-50">
                {isFeedbackFormVisible ? (
                   <div className="flex flex-col gap-2 items-end bg-white p-4 rounded-lg shadow-lg border w-full max-w-md">
                    <textarea
                      value={feedbackText}
                      onChange={(e) => setFeedbackText(e.target.value)}
                      placeholder="Type your feedback..."
                      className="border rounded px-2 py-1 w-full"
                      rows={3}
                    />
                    <div className="flex items-center gap-4">
                       <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={needsReview}
                          onChange={(e) => setNeedsReview(e.target.checked)}
                          className="rounded"
                        />
                        Mark as "Needs Review"
                      </label>
                      <button
                        onClick={handleSendFeedback}
                        disabled={!feedbackText || submissionStatus === 'sending'}
                        className="bg-green-500 text-white font-bold py-2 px-4 rounded-full disabled:bg-gray-400 hover:bg-green-600 transition"
                      >
                        {submissionStatus === 'sending' ? 'Sending...' : 'Submit Feedback'}
                      </button>
                      <button
                        onClick={() => setIsFeedbackFormVisible(false)}
                        className="bg-gray-200 text-gray-800 font-bold py-2 px-4 rounded-full hover:bg-gray-300 transition"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="text-right">
                    <button
                      onClick={() => setIsFeedbackFormVisible(true)}
                      className="bg-blue-600 text-white font-bold py-2 px-6 rounded-full shadow-lg hover:bg-blue-700 transition"
                    >
                      Add/Update Feedback
                    </button>
                    <p className="text-xs text-gray-500 mt-1 max-w-xs">
                      This will send this log with your feedback to the developers.
                    </p>
                  </div>
                )}
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