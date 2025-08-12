import { useEffect, useMemo, useRef, useState } from 'react';
import {
  loadStarterPrompt,
  markStarterPromptConsumed,
  savePendingStarterPrompt,
  StarterChatPrompt,
  StarterPromptEntry,
} from '../lib/starterPromptStorage';

type StarterChatAny = {
  mode: 'auto' | 'prompt';
  message: string;
  responses?: { label: string; message: string }[];
};

export type UseStarterPromptResult = {
  pendingStarter: StarterChatPrompt | null;
  markConsumedIfAny: () => void;
};

export function useStarterPrompt(
  workflowId: string,
  initialStarterChat?: StarterChatAny,
  userKey?: string
): UseStarterPromptResult {
  const [pendingStarter, setPendingStarter] = useState<StarterChatPrompt | null>(null);
  const initializedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!workflowId) return;
    // Avoid double-running for the same workflowId
    if (initializedRef.current === workflowId) return;
    initializedRef.current = workflowId;

    if (initialStarterChat?.mode === 'prompt') {
      // Persist prompt-mode starter chat (idempotent save)
      savePendingStarterPrompt(workflowId, {
        mode: 'prompt',
        message: initialStarterChat.message,
        responses: initialStarterChat.responses,
      }, userKey);
    }

    const entry: StarterPromptEntry | null = loadStarterPrompt(workflowId, userKey);
    if (entry && entry.consumed === false) {
      setPendingStarter(entry.starter_chat);
    } else {
      setPendingStarter(null);
    }
  }, [workflowId, initialStarterChat?.mode, initialStarterChat?.message, userKey]);

  const markConsumedIfAny = useMemo(() => {
    return () => {
      if (!workflowId) return;
      if (!pendingStarter) return;
      markStarterPromptConsumed(workflowId, userKey);
      setPendingStarter(null);
    };
  }, [workflowId, userKey, pendingStarter]);

  return { pendingStarter, markConsumedIfAny };
}


