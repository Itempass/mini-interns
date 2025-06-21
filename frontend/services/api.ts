const API_URL = '/api'; // The backend is on port 5001, but we're proxying

export interface AppSettings {
  IMAP_SERVER?: string;
  IMAP_USERNAME?: string;
  IMAP_PASSWORD?: string;
  OPENROUTER_API_KEY?: string;
  OPENROUTER_MODEL?: string;
  DRAFT_CREATION_ENABLED?: boolean;
}

export interface FilterRules {
  email_blacklist: string[];
  email_whitelist: string[];
  domain_blacklist: string[];
  domain_whitelist: string[];
}

export interface AgentSettings {
  system_prompt?: string;
  trigger_conditions?: string;
  user_context?: string;
  filter_rules?: FilterRules;
  agent_steps?: string;
  agent_instructions?: string;
}

export const getSettings = async (): Promise<AppSettings> => {
  console.log('Fetching settings from URL:', `${API_URL}/settings`);
  try {
    const response = await fetch(`${API_URL}/settings`);
    if (!response.ok) {
      console.error('Failed to fetch settings. Status:', response.status);
      throw new Error('Failed to fetch settings');
    }
    const data = await response.json();
    console.log('Successfully fetched settings:', data);
    return data;
  } catch (error) {
    console.error('An error occurred while fetching settings:', error);
    return {};
  }
};

export const setSettings = async (settings: AppSettings) => {
  console.log('Setting settings:', settings);
  try {
    const response = await fetch(`${API_URL}/settings`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(settings),
    });
    if (!response.ok) {
      console.error('Failed to set settings. Status:', response.status);
      throw new Error('Failed to set settings');
    }
    const result = await response.json();
    console.log('Successfully set settings:', result);
    return result;
  } catch (error) {
    console.error('An error occurred while setting settings:', error);
    return null;
  }
};

export const getAgentSettings = async (): Promise<AgentSettings> => {
  console.log('Fetching agent settings from URL:', `${API_URL}/agent/settings`);
  try {
    const response = await fetch(`${API_URL}/agent/settings`);
    if (!response.ok) {
      console.error('Failed to fetch agent settings. Status:', response.status);
      throw new Error('Failed to fetch agent settings');
    }
    const data = await response.json();
    console.log('Successfully fetched agent settings:', data);
    return data;
  } catch (error) {
    console.error('An error occurred while fetching agent settings:', error);
    return {};
  }
};

export const setAgentSettings = async (settings: AgentSettings) => {
  console.log('Setting agent settings:', settings);
  try {
    const response = await fetch(`${API_URL}/agent/settings`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(settings),
    });
    if (!response.ok) {
      console.error('Failed to set agent settings. Status:', response.status);
      throw new Error('Failed to set agent settings');
    }
    const result = await response.json();
    console.log('Successfully set agent settings:', result);
    return result;
  } catch (error) {
    console.error('An error occurred while setting agent settings:', error);
    return null;
  }
};

export const initializeInbox = async () => {
  console.log('Initializing inbox...');
  try {
    const response = await fetch(`${API_URL}/agent/initialize-inbox`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    if (!response.ok) {
      console.error('Failed to initialize inbox. Status:', response.status);
      throw new Error('Failed to initialize inbox');
    }
    const result = await response.json();
    console.log('Successfully triggered inbox initialization:', result);
    return result;
  } catch (error) {
    console.error('An error occurred while initializing inbox:', error);
    return null;
  }
};

export const getInboxInitializationStatus = async (): Promise<string> => {
  try {
    const response = await fetch(`${API_URL}/agent/initialize-inbox/status`);
    if (!response.ok) {
      console.error('Failed to fetch inbox status. Status:', response.status);
      throw new Error('Failed to fetch inbox status');
    }
    const data = await response.json();
    return data.status;
  } catch (error) {
    console.error('An error occurred while fetching inbox status:', error);
    return 'error';
  }
};

export const getOpenRouterModel = async () => {
  const settings = await getSettings();
  return settings.OPENROUTER_MODEL || '';
};

export const setOpenRouterModel = async (model: string) => {
  return await setSettings({ OPENROUTER_MODEL: model });
};

// Agent Logger API
export interface ConversationData {
  metadata: {
    conversation_id: string;
    [key: string]: any;
  };
  messages: Array<{
    content: string;
    role: string;
    [key: string]: any;
  }>;
}

export interface ConversationsResponse {
  conversations: ConversationData[];
  count: number;
}

export interface ConversationResponse {
  conversation: ConversationData;
}

export const getConversations = async (): Promise<ConversationsResponse> => {
  console.log('Fetching conversations...');
  try {
    const response = await fetch(`${API_URL}/agentlogger/conversations`);
    if (!response.ok) {
      console.error('Failed to fetch conversations. Status:', response.status);
      throw new Error('Failed to fetch conversations');
    }
    const data = await response.json();
    console.log('Successfully fetched conversations:', data);
    return data;
  } catch (error) {
    console.error('An error occurred while fetching conversations:', error);
    return { conversations: [], count: 0 };
  }
};

export const getConversation = async (conversationId: string): Promise<ConversationData | null> => {
  console.log('Fetching conversation:', conversationId);
  try {
    const response = await fetch(`${API_URL}/agentlogger/conversations/${conversationId}`);
    if (!response.ok) {
      console.error('Failed to fetch conversation. Status:', response.status);
      if (response.status === 404) {
        return null;
      }
      throw new Error('Failed to fetch conversation');
    }
    const data = await response.json();
    console.log('Successfully fetched conversation:', data);
    return data.conversation;
  } catch (error) {
    console.error('An error occurred while fetching conversation:', error);
    return null;
  }
};

export interface McpTool {
  name: string;
  description: string;
  inputSchema: Record<string, any>;
}

export interface McpServer {
  name: string;
  port: number;
  url: string;
  tools: McpTool[];
}

export const getMcpServers = async (): Promise<McpServer[]> => {
  console.log('Fetching MCP servers...');
  try {
    const response = await fetch(`${API_URL}/mcp/servers`);
    if (!response.ok) {
      console.error('Failed to fetch MCP servers. Status:', response.status);
      throw new Error('Failed to fetch MCP servers');
    }
    const data = await response.json();
    console.log('Successfully fetched MCP servers:', data);
    return data;
  } catch (error) {
    console.error('An error occurred while fetching MCP servers:', error);
    return [];
  }
}; 