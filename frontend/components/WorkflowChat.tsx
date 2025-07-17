'use client';

import React, { useState, useEffect, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { ChatMessage, runWorkflowAgentChatStep } from '../services/workflows_api';
import { Send, Bot, User, Loader2, Square } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface WorkflowChatProps {
  workflowId: string;
  onWorkflowUpdate: () => void;
  onBusyStatusChange?: (isBusy: boolean) => void;
}

const WorkflowChat: React.FC<WorkflowChatProps> = ({ workflowId, onWorkflowUpdate, onBusyStatusChange }) => {
  const [conversationId, setConversationId] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [userInput, setUserInput] = useState('');
  const [isAgentThinking, setIsAgentThinking] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    onBusyStatusChange?.(isAgentThinking);
  }, [isAgentThinking, onBusyStatusChange]);

  useEffect(() => {
    const newConversationId = uuidv4();
    setConversationId(newConversationId);
    setMessages([
        { role: 'assistant', content: "Hello! I'll help you create a workflow. Please describe to me what you want to make." }
    ]);
  }, [workflowId]); 

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isAgentThinking]);

  useEffect(() => {
    autoResize();
  }, [userInput]);

  useEffect(() => {
    autoResize();
  }, []);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userInput.trim() || isAgentThinking) return;

    const userMessage: ChatMessage = { role: 'user', content: userInput };
    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setUserInput('');
    setIsAgentThinking(true);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    await runConversation(newMessages);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(e);
    }
  };

  const autoResize = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '2.5rem';
      const maxHeight = 192; // 12rem
      const newHeight = Math.min(textareaRef.current.scrollHeight, maxHeight);
      textareaRef.current.style.height = `${newHeight}px`;
      
      // Only show scroll bar when content exceeds max height
      textareaRef.current.style.overflowY = textareaRef.current.scrollHeight > maxHeight ? 'auto' : 'hidden';
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setUserInput(e.target.value);
    autoResize();
  };

  const handleInterrupt = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsAgentThinking(false);
    }
  };

  const runConversation = async (currentMessages: ChatMessage[]) => {
    let conversationState = currentMessages;
    let isComplete = false;

    while (!isComplete) {
      const response = await runWorkflowAgentChatStep(
        workflowId,
        {
          conversation_id: conversationId,
          messages: conversationState,
        },
        abortControllerRef.current?.signal
      );

      if (response === 'aborted') {
        console.log('Conversation interrupted by user.');
        break;
      }

      if (response) {
        conversationState = response.messages;
        setMessages(conversationState);
        isComplete = response.is_complete;
        
        onWorkflowUpdate();
      } else {
        // Handle API error
        const errorMessage: ChatMessage = {
          role: 'assistant',
          content: "Sorry, I encountered an error and can't continue. Please check the server logs.",
        };
        setMessages([...conversationState, errorMessage]);
        isComplete = true; // Stop the loop on error
      }
    }
    setIsAgentThinking(false);
  };

  const renderMessageContent = (message: ChatMessage) => {
    if (message.role === 'assistant' && message.tool_calls) {
      return (
        <div className="text-gray-500 italic">
          Thinking... (using tool: {message.tool_calls[0].function.name})
        </div>
      );
    }
    return (
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown 
          components={{
            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
            code: ({ children }) => <code className="bg-gray-100 px-1 py-0.5 rounded text-sm">{children}</code>,
            pre: ({ children }) => <pre className="bg-gray-100 p-2 rounded overflow-x-auto">{children}</pre>,
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
    );
  };
  
  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-gray-200 flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center"><Bot className="mr-2" /> Workflow Agent</h3>
        {isAgentThinking && <Loader2 className="w-5 h-5 animate-spin text-gray-500" />}
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, index) => (
            <div key={index} className={`flex items-start gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                {msg.role !== 'user' && msg.role !== 'tool' && <Bot className="w-6 h-6 text-blue-500" />}
                {msg.role === 'user' && <User className="w-6 h-6 text-green-500" />}
                
                {msg.role !== 'tool' && (
                    <div className={`px-4 py-2 rounded-lg max-w-lg ${msg.role === 'user' ? 'bg-green-100 text-green-900' : 'bg-blue-100 text-blue-900'}`}>
                        {renderMessageContent(msg)}
                    </div>
                )}
            </div>
        ))}
        {isAgentThinking && (
            <div className="flex items-start gap-3">
                <Bot className="w-6 h-6 text-blue-500" />
                <div className="px-4 py-2 rounded-lg bg-blue-100 text-blue-900">
                    <Loader2 className="w-5 h-5 animate-spin" />
                </div>
            </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="p-4 border-t border-gray-200">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={userInput}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Tell the agent what to do..."
            className="flex-1 p-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none leading-normal whitespace-pre-wrap"
            disabled={isAgentThinking}
            style={{ minHeight: '2.5rem', height: '2.5rem', maxHeight: '12rem', overflowY: 'hidden' }}
          />
          {isAgentThinking ? (
            <button
              type="button"
              onClick={handleInterrupt}
              className="p-2 bg-red-500 text-white rounded-lg hover:bg-red-600"
            >
              <Square className="w-5 h-5" />
            </button>
          ) : (
            <button
              type="submit"
              className="p-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-400"
              disabled={!userInput.trim()}
            >
              <Send className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default WorkflowChat; 