'use client';

import React, { useState, useEffect } from 'react';
import { LogEntry, addReview } from '../services/api';

type SubmissionStatus = 'idle' | 'submitting' | 'success' | 'error';

interface FeedbackFormProps {
  log: LogEntry;
}

const FeedbackForm: React.FC<FeedbackFormProps> = ({ log }) => {
  const [feedbackText, setFeedbackText] = useState(log.feedback || '');
  const [submissionStatus, setSubmissionStatus] = useState<SubmissionStatus>('idle');
  const [submissionMessage, setSubmissionMessage] = useState('');
  const [isFormVisible, setIsFormVisible] = useState(false);

  useEffect(() => {
    if (submissionStatus === 'success' || submissionStatus === 'error') {
      const timer = setTimeout(() => {
        if (submissionStatus === 'success') {
          setFeedbackText('');
          setIsFormVisible(false); // Revert to the button after success
        }
        setSubmissionStatus('idle');
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [submissionStatus]);

  const handleFeedbackSubmit = async () => {
    if (!feedbackText) return;
    setSubmissionStatus('submitting');
    const result = await addReview(log.id, feedbackText, true, log);
    if (result.success) {
      setSubmissionStatus('success');
      setSubmissionMessage('Feedback submitted successfully!');
    } else {
      setSubmissionStatus('error');
      setSubmissionMessage(result.error || 'Failed to submit feedback.');
    }
  };

  if (submissionStatus === 'success') {
    return (
      <div className="p-4 bg-green-100 text-green-800 rounded-lg">
        <p className="font-bold">Thank you!</p>
        <p>{submissionMessage}</p>
      </div>
    );
  }

  if (submissionStatus === 'error') {
    return (
      <div className="p-4 bg-red-100 text-red-800 rounded-lg">
        <p className="font-bold">Error</p>
        <p>{submissionMessage}</p>
      </div>
    );
  }

  if (!isFormVisible) {
    return (
      <div className="text-right">
        <button
          onClick={() => setIsFormVisible(true)}
          className="bg-blue-600 text-white font-bold py-2 px-6 rounded-full shadow-lg hover:bg-blue-700 transition"
        >
          Send Feedback to Developers
        </button>
        <p className="text-xs text-gray-500 mt-1 max-w-xs">
          This will send this log with your feedback to the developers.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 items-end bg-white p-4 rounded-lg shadow-lg border w-full max-w-md">
      <textarea
        value={feedbackText}
        onChange={(e) => setFeedbackText(e.target.value)}
        placeholder="Type your feedback..."
        className="border rounded px-2 py-1 w-full"
        rows={3}
      />
      <div className="flex items-center gap-4">
         <button
          onClick={handleFeedbackSubmit}
          disabled={!feedbackText || submissionStatus === 'submitting'}
          className="bg-green-500 text-white font-bold py-2 px-4 rounded-full disabled:bg-gray-400 hover:bg-green-600 transition"
        >
          {submissionStatus === 'submitting' ? 'Submitting...' : 'Send Feedback'}
        </button>
        <button
          onClick={() => setIsFormVisible(false)}
          className="bg-gray-200 text-gray-800 font-bold py-2 px-4 rounded-full hover:bg-gray-300 transition"
        >
          Cancel
        </button>
      </div>
    </div>
  );
};

export default FeedbackForm; 