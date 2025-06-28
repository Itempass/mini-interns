const API_URL = '/api'; // The backend is on port 5001, but we're proxying

export interface AppSettings {
  IMAP_SERVER?: string;
  IMAP_USERNAME?: string;
  IMAP_PASSWORD?: string;
  OPENROUTER_API_KEY?: string;
  OPENROUTER_MODEL?: string;
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
  agent_tools?: { [key: string]: { enabled: boolean; required: boolean; order?: number } };
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

export const testImapConnection = async () => {
  console.log('Testing IMAP connection...');
  try {
    const response = await fetch(`${API_URL}/test_imap_connection`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    const result = await response.json();
    if (!response.ok) {
      console.error('IMAP connection test failed. Status:', response.status, 'Details:', result.detail);
      throw new Error(result.detail || 'Failed to test IMAP connection');
    }
    console.log('Successfully tested IMAP connection:', result);
    return result;
  } catch (error) {
    console.error('An error occurred while testing IMAP connection:', error);
    throw error;
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

export const reinitializeInbox = async () => {
  console.log('Re-initializing inbox...');
  try {
    const response = await fetch(`${API_URL}/agent/reinitialize-inbox`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    if (!response.ok) {
      console.error('Failed to re-initialize inbox. Status:', response.status);
      throw new Error('Failed to re-initialize inbox');
    }
    const result = await response.json();
    console.log('Successfully triggered inbox re-initialization:', result);
    return result;
  } catch (error) {
    console.error('An error occurred while re-initializing inbox:', error);
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

export const addReview = async (conversationId: string, feedback: string): Promise<{ success: boolean; error?: string }> => {
  console.log(`Adding review for conversation ${conversationId}...`);
  try {
    const response = await fetch(`${API_URL}/agentlogger/conversations/${conversationId}/review`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ feedback }),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Failed to add review' }));
      console.error('Failed to add review. Status:', response.status, 'Details:', errorData.detail);
      throw new Error(errorData.detail || 'Failed to add review');
    }
    console.log('Successfully added review.');
    return { success: true };
  } catch (error: any) {
    console.error('An error occurred while adding review:', error);
    return { success: false, error: error.message };
  }
};

// MCP API
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

// --- New Agent Management API ---

export interface Agent {
  uuid: string;
  name: string;
  description: string;
  system_prompt: string;
  user_instructions: string;
  tools: { [key: string]: { enabled: boolean; required: boolean; order?: number } };
  paused?: boolean;
  created_at: string;
  updated_at: string;
  trigger_conditions?: string;
  filter_rules?: FilterRules;
  trigger_bypass?: boolean;
}

export interface CreateAgentRequest {
  name: string;
  description: string;
}

export interface Tool {
  id: string;
  name: string;
  description: string;
  server: string;
  input_schema: Record<string, any>;
}

export interface Template {
  id: string;
  name: string;
  description: string;
}

export const getAgents = async (): Promise<Agent[]> => {
  try {
    const response = await fetch(`${API_URL}/agents`);
    if (!response.ok) throw new Error('Failed to fetch agents');
    return await response.json();
  } catch (error) {
    console.error('Error fetching agents:', error);
    return [];
  }
};

export const getAgent = async (uuid: string): Promise<Agent | null> => {
  try {
    const response = await fetch(`${API_URL}/agents/${uuid}`);
    if (!response.ok) throw new Error('Failed to fetch agent');
    const data = await response.json();
    console.log(`[getAgent] Fetched data for agent ${uuid}:`, data);
    return data;
  } catch (error) {
    console.error(`Error fetching agent ${uuid}:`, error);
    return null;
  }
};

export const updateAgent = async (agent: Agent): Promise<Agent | null> => {
  try {
    const response = await fetch(`${API_URL}/agents/${agent.uuid}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(agent),
    });
    if (!response.ok) throw new Error('Failed to update agent');
    return await response.json();
  } catch (error) {
    console.error(`Error updating agent ${agent.uuid}:`, error);
    return null;
  }
};

export const createAgent = async (agentData: CreateAgentRequest): Promise<Agent | null> => {
  try {
    const response = await fetch(`${API_URL}/agents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(agentData),
    });
    if (!response.ok) throw new Error('Failed to create agent');
    return await response.json();
  } catch (error) {
    console.error('Error creating agent:', error);
    return null;
  }
};

export const deleteAgent = async (uuid: string): Promise<void> => {
  try {
    const response = await fetch(`${API_URL}/agents/${uuid}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete agent');
  } catch (error) {
    console.error(`Error deleting agent ${uuid}:`, error);
    throw error;
  }
};

export const getTools = async (): Promise<Tool[]> => {
  const response = await fetch('/api/tools');
  if (!response.ok) {
    throw new Error('Failed to fetch tools');
  }
  return response.json();
};

export const exportAgent = async (agentId: string) => {
  const response = await fetch(`/api/agents/${agentId}/export`);
  if (!response.ok) {
    throw new Error('Failed to export agent');
  }
  const blob = await response.blob();
  const contentDisposition = response.headers.get('content-disposition');
  let filename = 'agent.json';
  if (contentDisposition) {
    const filenameMatch = contentDisposition.match(/filename="(.+?)"/);
    if (filenameMatch && filenameMatch.length > 1) {
      filename = filenameMatch[1];
    }
  }
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
};

export const importAgent = async (file: File): Promise<Agent> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/agents/import', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to import agent' }));
    throw new Error(errorData.detail);
  }

  return response.json();
};

export const getAgentTemplates = async (): Promise<Template[]> => {
  const response = await fetch('/api/agents/templates');
  if (!response.ok) {
    throw new Error('Failed to fetch agent templates');
  }
  return response.json();
};

export const createAgentFromTemplate = async (templateId: string): Promise<Agent> => {
  const response = await fetch('/api/agents/from-template', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ template_id: templateId }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to create agent from template' }));
    throw new Error(errorData.detail);
  }

  return response.json();
}; 