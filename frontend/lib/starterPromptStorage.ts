// Utilities for persisting starter prompt state in localStorage (frontend-only)

export type StarterChatPrompt = {
  mode: 'prompt';
  message: string;
  responses?: { label: string; message: string }[];
};

export type StarterPromptEntry = {
  version: 1;
  consumed: boolean;
  starter_chat: StarterChatPrompt;
  saved_at: string; // ISO timestamp
};

function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function storageKey(workflowId: string, userKey?: string): string {
  const base = `starter_prompt:${workflowId}`;
  return userKey ? `${base}:${userKey}` : base;
}

export function savePendingStarterPrompt(
  workflowId: string,
  starterChat: StarterChatPrompt,
  userKey?: string
): void {
  if (!isBrowser()) return;
  try {
    const key = storageKey(workflowId, userKey);
    const existingRaw = window.localStorage.getItem(key);
    if (existingRaw) {
      // Do not overwrite if already present and not consumed
      const existing: StarterPromptEntry | null = JSON.parse(existingRaw);
      if (existing && existing.consumed === false) return;
    }
    const entry: StarterPromptEntry = {
      version: 1,
      consumed: false,
      starter_chat: starterChat,
      saved_at: new Date().toISOString(),
    };
    window.localStorage.setItem(key, JSON.stringify(entry));
  } catch {
    // Ignore storage errors
  }
}

export function loadStarterPrompt(
  workflowId: string,
  userKey?: string
): StarterPromptEntry | null {
  if (!isBrowser()) return null;
  try {
    const key = storageKey(workflowId, userKey);
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed: StarterPromptEntry = JSON.parse(raw);
    if (!parsed || parsed.version !== 1) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function markStarterPromptConsumed(
  workflowId: string,
  userKey?: string
): void {
  if (!isBrowser()) return;
  try {
    const key = storageKey(workflowId, userKey);
    const entry = loadStarterPrompt(workflowId, userKey);
    if (!entry) return;
    if (entry.consumed) return;
    entry.consumed = true;
    window.localStorage.setItem(key, JSON.stringify(entry));
  } catch {
    // Ignore storage errors
  }
}

export function clearStarterPrompt(workflowId: string, userKey?: string): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.removeItem(storageKey(workflowId, userKey));
  } catch {
    // Ignore storage errors
  }
}


