export const API_URL = '/api'; // The backend is on port 5001, but we're proxying

// --- Auth ---

export const login = async (password: string): Promise<boolean> => {
  try {
    const response = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    return response.ok;
  } catch (error) {
    console.error('Login request failed:', error);
    return false;
  }
};

export type AuthStatus = "self_set_configured" | "self_set_unconfigured" | "legacy_configured" | "unconfigured";

export const getAuthStatus = async (): Promise<AuthStatus> => {
  try {
    const response = await fetch(`${API_URL}/auth/status`, { cache: 'no-store' });
    if (!response.ok) {
      return "unconfigured";
    }
    const data = await response.json();
    return data.status;
  } catch (error) {
    console.error('Auth status request failed:', error);
    return "unconfigured";
  }
};

export const setPassword = async (password: string): Promise<{success: boolean, message?: string}> => {
  try {
    const response = await fetch(`${API_URL}/auth/set-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    if (response.ok) {
      return { success: true };
    }
    const errorData = await response.json();
    return { success: false, message: errorData.detail || 'Failed to set password.' };
  } catch (error) {
    console.error('Set password request failed:', error);
    return { success: false, message: 'An unexpected error occurred.' };
  }
};

export const verifyToken = async (token: string): Promise<boolean> => {
  try {
    const response = await fetch(`${API_URL}/auth/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    if (!response.ok) {
      return false;
    }
    const data = await response.json();
    return data.valid === true;
  } catch (error) {
    console.error('Token verification request failed:', error);
    return false;
  }
};

// --- End Auth ---

export interface AppSettings {
  IMAP_SERVER?: string;
  IMAP_USERNAME?: string;
  IMAP_PASSWORD?: string;
  EMBEDDING_MODEL?: string;
}

export interface EmbeddingModel {
  provider: string;
  model_name: string;
  vector_size: number;
  max_input_tokens: number;
  max_batch_size: number;
  max_batch_tokens: number | null;
  default: boolean;
  model_name_from_key: string;
  api_key_provided: boolean;
}

export interface FilterRules {
  email_blacklist: string[];
  email_whitelist: string[];
  domain_blacklist: string[];
  domain_whitelist: string[];
}

export const getSettings = async (): Promise<{ settings: AppSettings, embeddingModels: EmbeddingModel[] }> => {
  console.log('Fetching settings from URL:', `${API_URL}/settings`);
  try {
    const response = await fetch(`${API_URL}/settings`);
    if (!response.ok) {
      console.error('Failed to fetch settings. Status:', response.status);
      throw new Error('Failed to fetch settings');
    }
    const data = await response.json();
    console.log('Successfully fetched settings:', data);
    return { settings: data.settings, embeddingModels: data.embedding_models };
  } catch (error) {
    console.error('An error occurred while fetching settings:', error);
    return { settings: {}, embeddingModels: [] };
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

export const getVersion = async (): Promise<string> => {
  console.log('Fetching version from URL:', `${API_URL}/version`);
  try {
    const response = await fetch(`${API_URL}/version`);
    if (!response.ok) {
      console.error('Failed to fetch version. Status:', response.status);
      throw new Error('Failed to fetch version');
    }
    const data = await response.json();
    console.log('Successfully fetched version:', data.version);
    return data.version;
  } catch (error) {
    console.error('An error occurred while fetching version:', error);
    return 'unknown';
  }
};

export const getLatestVersion = async (): Promise<string | null> => {
  console.log('Fetching latest version from URL:', `${API_URL}/version/latest`);
  try {
    const response = await fetch(`${API_URL}/version/latest`);
    if (!response.ok) {
      console.error('Failed to fetch latest version. Status:', response.status);
      throw new Error('Failed to fetch latest version');
    }
    const data = await response.json();
    console.log('Successfully fetched latest version:', data.latest_version);
    return data.latest_version;
  } catch (error) {
    console.error('An error occurred while fetching latest version:', error);
    return null;
  }
};

export const checkBackendHealth = async (): Promise<boolean> => {
  try {
    const response = await fetch(`${API_URL}/`);
    return response.ok;
  } catch (error) {
    return false;
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

// Note: OpenRouter model functions removed as models are now per-agent/trigger

// Agent Logger API
export interface LogMessage {
  content: string | null;
  role: string;
  tool_calls?: any[];
  [key: string]: any;
}

export interface LogEntry {
  id: string;
  reference_string: string | null;
  log_type: 'workflow' | 'custom_agent' | 'custom_llm' | 'workflow_agent';
  workflow_id: string | null;
  workflow_instance_id: string | null;
  workflow_name: string | null;
  step_id: string | null;
  step_instance_id: string | null;
  step_name: string | null;
  messages: LogMessage[] | null;
  needs_review: boolean | null;
  feedback: string | null;
  start_time: string; // ISO 8601 format
  end_time: string | null; // ISO 8601 format
  anonymized: boolean;
  [key: string]: any;
}

export interface LogEntriesResponse {
  log_entries: LogEntry[];
  count: number;
}

export interface GroupedLog {
  workflow_log: LogEntry;
  step_logs: LogEntry[];
}

export interface GroupedLogEntriesResponse {
  workflows: GroupedLog[];
  total_workflows: number;
}

export const getLogEntries = async (): Promise<LogEntriesResponse> => {
  try {
    const response = await fetch(`${API_URL}/agentlogger/logs`);
    if (!response.ok) {
      throw new Error('Failed to fetch logs');
    }
    return await response.json();
  } catch (error) {
    console.error('An error occurred while fetching logs:', error);
    return { log_entries: [], count: 0 };
  }
};

export const getGroupedLogEntries = async (limit: number, offset: number, workflowId?: string): Promise<GroupedLogEntriesResponse> => {
  try {
    let url = `${API_URL}/agentlogger/logs/grouped?limit=${limit}&offset=${offset}`;
    if (workflowId) {
      url += `&workflow_id=${workflowId}`;
    }
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error('Failed to fetch grouped logs');
    }
    return await response.json();
  } catch (error) {
    console.error('An error occurred while fetching grouped logs:', error);
    return { workflows: [], total_workflows: 0 };
  }
};

export const getLogEntry = async (logId: string): Promise<LogEntry | null> => {
  try {
    const response = await fetch(`${API_URL}/agentlogger/logs/${logId}`);
    if (!response.ok) {
      throw new Error('Failed to fetch log entry');
    }
    const data = await response.json();
    return data.log_entry;
  } catch (error) {
    console.error('An error occurred while fetching log entry:', error);
    return null;
  }
};

export const addReview = async (logId: string, feedback: string, needs_review: boolean, logData?: LogEntry): Promise<{ success: boolean; error?: string }> => {
  try {
    const response = await fetch(`${API_URL}/agentlogger/logs/${logId}/review`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ feedback, needs_review, log_data: logData }),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Failed to add review' }));
      throw new Error(errorData.detail || 'Failed to add review');
    }
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

export interface ParamSchemaField {
  parameter_key: string;
  display_text: string;
  type: 'text' | 'checkbox' | 'list' | 'textarea' | 'key_value_field_one_line';
  injection_key?: string;
  item_schema?: ParamSchemaField[];
}

export interface Agent {
  uuid: string;
  name: string;
  description: string;
  system_prompt: string;
  user_instructions: string;
  tools: { [key: string]: { enabled: boolean; required: boolean; order?: number } };
  paused?: boolean;
  model: string;
  param_schema?: ParamSchemaField[];
  param_values?: { [key: string]: any };
  use_abstracted_editor?: boolean;
  created_at: string;
  updated_at: string;
  template_id?: string;
  template_version?: string;
  trigger_conditions?: string;
  filter_rules?: FilterRules;
  trigger_bypass?: boolean;
  trigger_model: string;
}

export interface CreateAgentRequest {
  name: string;
  description: string;
  model?: string;
  trigger_model?: string;
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

export const generateLabelDescriptions = async (agentUuid: string): Promise<Agent | null> => {
  try {
    const response = await fetch(`${API_URL}/agents/${agentUuid}/generate-descriptions`, {
      method: 'POST',
    });
    if (!response.ok) throw new Error('Failed to start description generation');
    return await response.json();
  } catch (error) {
    console.error(`Error starting description generation for agent ${agentUuid}:`, error);
    return null;
  }
};

export const applyTemplateDefaults = async (agentUuid: string): Promise<Agent | null> => {
  try {
    const response = await fetch(`${API_URL}/agents/${agentUuid}/apply-template-defaults`, {
      method: 'POST',
    });
    if (!response.ok) throw new Error('Failed to apply template defaults');
    return await response.json();
  } catch (error) {
    console.error(`Error applying template defaults for agent ${agentUuid}:`, error);
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

export const getToneOfVoiceProfile = async (): Promise<any> => {
  try {
    const response = await fetch(`${API_URL}/settings/tone-of-voice`);
    if (!response.ok) {
      throw new Error("Failed to fetch tone of voice profile");
    }
    return await response.json();
  } catch (error) {
    console.error("Error fetching tone of voice profile:", error);
    return null;
  }
};

export const getToneOfVoiceStatus = async (): Promise<string> => {
  try {
    const response = await fetch(`${API_URL}/settings/tone-of-voice/status`);
    if (!response.ok) {
      console.error('Failed to fetch tone of voice status. Status:', response.status);
      throw new Error('Failed to fetch tone of voice status');
    }
    const data = await response.json();
    return data.status;
  } catch (error) {
    console.error('An error occurred while fetching tone of voice status:', error);
    return 'error';
  }
};

export const rerunToneAnalysis = async (): Promise<any> => {
  const response = await fetch(`${API_URL}/agent/rerun-tone-analysis`, {
    method: 'POST',
  });
  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Failed to start tone of voice analysis');
  }
  return response.json();
}; 