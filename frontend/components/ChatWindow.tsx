import React from 'react';

const ChatWindow = () => {
  return (
    <div className="flex flex-col h-full border-l border-gray-200 bg-gray-50">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-bold">Chat with Agent</h2>
      </div>
      <div className="flex-1 p-4 overflow-y-auto">
        {/* Example messages */}
        <div className="mb-4">
          <div className="flex items-end">
            <div className="bg-blue-500 text-white p-3 rounded-lg rounded-bl-none">
              <p className="text-sm">What was the last email about?</p>
            </div>
          </div>
        </div>
        <div className="mb-4">
          <div className="flex items-end justify-end">
            <div className="bg-gray-200 text-black p-3 rounded-lg rounded-br-none">
              <p className="text-sm">It was from your boss, asking about the Q3 report.</p>
            </div>
          </div>
        </div>
        <div className="mb-4">
          <div className="flex items-end">
            <div className="bg-blue-500 text-white p-3 rounded-lg rounded-bl-none">
              <p className="text-sm">Can you summarize it for me?</p>
            </div>
          </div>
        </div>
        <div className="mb-4">
          <div className="flex items-end justify-end">
            <div className="bg-gray-200 text-black p-3 rounded-lg rounded-br-none">
              <p className="text-sm">Subject: Q3 Report status. John Doe asks for an update on the Q3 report, and wants to know if the data from the marketing team has been included. He mentions a deadline of next Friday.</p>
            </div>
          </div>
        </div>
      </div>
      <div className="p-4 border-t border-gray-200 bg-white">
        <div className="relative">
          <input
            type="text"
            placeholder="Type your message..."
            className="w-full p-3 pr-10 border border-gray-300 rounded-full"
          />
          <button className="absolute inset-y-0 right-0 flex items-center pr-3">
            <svg className="w-5 h-5 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 1.414L10.586 9H7a1 1 0 100 2h3.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatWindow; 