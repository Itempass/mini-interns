'use client';
import React, { useState, useEffect } from 'react';
import LogsList from '../../components/LogsList';
import LogDetail from '../../components/LogDetail';
import TopBar from '../../components/TopBar';
import { addReview, getLogEntry, LogEntry } from '../../services/api';
import LogsSidebar from '../../components/LogsSidebar';
import FeedbackForm from '../../components/FeedbackForm';


type SubmissionStatus = 'idle' | 'sending' | 'success' | 'error';

const LogsPage = () => {
  const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isLoadingLog, setIsLoadingLog] = useState(false);

  const handleSelectLog = async (logId: string) => {
    setSelectedLogId(logId);
    setIsModalOpen(true);

    setIsLoadingLog(true);
    const data = await getLogEntry(logId);
    if (data) {
      setSelectedLog(data);
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

  return (
    <div className="flex flex-col h-screen relative bg-gray-50" style={{
      backgroundImage: 'radial-gradient(#E5E7EB 1px, transparent 1px)',
      backgroundSize: '24px 24px'
    }}>
      <TopBar />
      <div className="flex flex-1 overflow-hidden gap-4 p-4">
        <div className="w-64 flex-shrink-0 flex flex-col bg-white border border-gray-300 rounded-lg overflow-hidden shadow-md">
          <LogsSidebar />
        </div>

        <main className="flex-1 bg-white border border-gray-300 rounded-lg shadow-md flex flex-col overflow-hidden">
            <div className="p-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold">Agent Logs</h2>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
                <LogsList onSelectLog={handleSelectLog} />
            </div>
        </main>

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
                {selectedLog && <FeedbackForm log={selectedLog} />}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default LogsPage; 