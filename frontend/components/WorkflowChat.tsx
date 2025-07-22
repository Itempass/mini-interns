'use client';

import React, { useState, useEffect, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { ChatMessage, runWorkflowAgentChatStep, submitHumanInput, ChatStepResponse } from '../services/workflows_api';
import { Send, Bot, User, Loader2, Square } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import FeatureRequestForm from './chat_input/FeatureRequestForm';

interface WorkflowChatProps {
  workflowId: string;
  onWorkflowUpdate: () => void;
  onBusyStatusChange?: (isBusy: boolean) => void;
  initialChatMessage?: string;
  clearInitialChatMessage: () => void;
}

interface HumanInputRequest {
  type: string;
  tool_call_id: string;
  data: any;
}

const WorkflowChat: React.FC<WorkflowChatProps> = ({ workflowId, onWorkflowUpdate, onBusyStatusChange, initialChatMessage, clearInitialChatMessage }) => {
  const [conversationId, setConversationId] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [userInput, setUserInput] = useState('');
  const [isAgentThinking, setIsAgentThinking] = useState(false);
  const [humanInputRequest, setHumanInputRequest] = useState<HumanInputRequest | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const prevWorkflowId = useRef<string | null>(null);

  useEffect(() => {
    onBusyStatusChange?.(isAgentThinking);
  }, [isAgentThinking, onBusyStatusChange]);

  useEffect(() => {
    const welcomeMessage: ChatMessage = { role: 'assistant', content: "Hello! I'll help you create a workflow. Please describe to me what you want to make." };
    
    // Only reset and start a new conversation if the workflowId has actually changed.
    if (prevWorkflowId.current !== workflowId) {
      prevWorkflowId.current = workflowId;
      const newConversationId = uuidv4();
      setConversationId(newConversationId);
      
      if (initialChatMessage) {
        const userMessage: ChatMessage = { role: 'user', content: initialChatMessage };
        const newMessages = [welcomeMessage, userMessage];
        setMessages(newMessages);
        
        setIsAgentThinking(true);
        if (abortControllerRef.current) abortControllerRef.current.abort();
        abortControllerRef.current = new AbortController();

        runConversation(newMessages);
        clearInitialChatMessage();
      } else {
        setMessages([welcomeMessage]);
      }
    }
  }, [workflowId, initialChatMessage]);

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

  const handleFeatureRequestSubmit = async (formData: { name: string; description: string }) => {
    if (!humanInputRequest) return;

    setIsAgentThinking(true);

    const submission = {
      conversation_id: conversationId,
      messages: messages,
      tool_call_id: humanInputRequest.tool_call_id,
      user_input: formData,
    };

    try {
      const response = await submitHumanInput(workflowId, submission, abortControllerRef.current?.signal);
      
      if (response === 'aborted') {
        console.log('Submission interrupted by user.');
        setIsAgentThinking(false);
        return;
      }

      if (response) {
        setMessages(response.messages);
        setHumanInputRequest(null); // Clear the form request
        // The conversation continues from where it left off
        await runConversation(response.messages);
      } else {
        // Handle API error
        alert("Sorry, there was an error submitting your request. Please try again.");
        setIsAgentThinking(false);
      }
    } catch (error) {
      console.error("Submission failed:", error);
      alert("A critical error occurred. Please check the console and try again.");
      setIsAgentThinking(false);
    }
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
        // Check for human input request before continuing the loop
        if (response.human_input_required) {
          setMessages(response.messages);
          setHumanInputRequest(response.human_input_required);
          isComplete = true; // Stop the loop, wait for human input
        } else {
          conversationState = response.messages;
          setMessages(conversationState);
          isComplete = response.is_complete;
          onWorkflowUpdate();
        }
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

  const renderTextWithMarkdown = (content: string) => (
    <div className="prose prose-sm max-w-none">
      <ReactMarkdown
        components={{
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          code: ({ children }) => <code className="bg-gray-100 px-1 py-0.5 rounded text-sm">{children}</code>,
          pre: ({ children }) => <pre className="bg-gray-100 p-2 rounded overflow-x-auto">{children}</pre>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
  
  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-gray-200 flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center"><Bot className="mr-2" /> Workflow Agent</h3>
        {isAgentThinking && <Loader2 className="w-5 h-5 animate-spin text-gray-500" />}
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, index) => {
          if (msg.role === 'tool') return null; // Do not render tool results directly

          const hasContent = msg.content && msg.content.trim().length > 0;
          const hasToolCalls = msg.tool_calls && msg.tool_calls.length > 0;
          
          if (msg.role === 'user') {
            return (
              <div key={index} className="flex items-start gap-3 justify-end">
                <User className="w-6 h-6 text-green-500" />
                <div className="px-4 py-2 rounded-lg max-w-lg bg-green-100 text-green-900">
                  {renderTextWithMarkdown(msg.content)}
                </div>
              </div>
            );
          }

          if (msg.role === 'assistant') {
            return (
              <div key={index} className="flex flex-col items-start gap-2">
                {/* Render assistant's text content WITH icon if it exists */}
                {hasContent && (
                  <div className="flex items-start gap-3">
                    <Bot className="w-6 h-6 text-blue-500" />
                    <div className="px-4 py-2 rounded-lg max-w-lg bg-blue-100 text-blue-900">
                      {renderTextWithMarkdown(msg.content)}
                    </div>
                  </div>
                )}
                {/* Render tool call information if it exists */}
                {hasToolCalls && msg.tool_calls.map((tool_call, tool_index) => (
                  <div key={tool_index} className="flex items-start gap-3">
                    {/* This spacer will indent the tool call to align with the message bubble, if a message bubble is present. */}
                    {hasContent && <div className="w-6 h-6 flex-shrink-0" />}
                    <div className={`px-4 py-2 rounded-lg max-w-lg bg-gray-100 text-gray-600 italic ${!hasContent ? 'ml-9' : ''}`}>
                      Using tool: {tool_call.function.name}
                    </div>
                  </div>
                ))}
              </div>
            );
          }
          
          return null;
        })}
        {humanInputRequest && (
          <div className="flex items-start gap-3">
            <Bot className="w-6 h-6 text-blue-500" />
            <div className="px-4 py-2 rounded-lg max-w-lg bg-blue-100 text-blue-900 w-full">
              <FeatureRequestForm
                request={humanInputRequest}
                onSubmit={handleFeatureRequestSubmit}
                isSubmitting={isAgentThinking}
              />
            </div>
          </div>
        )}
        {isAgentThinking && !humanInputRequest && (
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
              placeholder={humanInputRequest ? "Please fill out the form above to continue." : "Tell the agent what to do..."}
              className="flex-1 p-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none leading-normal whitespace-pre-wrap"
              disabled={isAgentThinking || humanInputRequest !== null}
              style={{ minHeight: '2.5rem', height: '2.5rem', maxHeight: '12rem', overflowY: 'hidden' }}
            />
            {isAgentThinking && !humanInputRequest ? (
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
                onClick={handleSendMessage}
                className="p-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-400"
                disabled={!userInput.trim() || humanInputRequest !== null}
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