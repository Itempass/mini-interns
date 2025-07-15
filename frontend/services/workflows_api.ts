const API_URL = '/api';

export interface Workflow {
    uuid: string;
    user_id: string;
    name: string;
    description: string;
    is_active: boolean;
    trigger_uuid: string | null;
    steps: string[];
    template_id: string | null;
    template_version: string | null;
    created_at: string;
    updated_at: string;
}

export interface TriggerModel {
    uuid: string;
    user_id: string;
    workflow_uuid: string;
    filter_rules: any;
    initial_data_description: string;
    created_at: string;
    updated_at: string;
}

export interface CustomLLMStep {
    uuid: string;
    user_id: string;
    name: string;
    description: string;
    type: 'custom_llm';
    model: string;
    system_prompt: string;
    generated_summary?: string;
}

export interface CustomAgentStep {
    uuid: string;
    user_id: string;
    name: string;
    description: string;
    type: 'custom_agent';
    model: string;
    system_prompt: string;
    tools: Record<string, any>;
    generated_summary?: string;
}

export interface StopWorkflowCondition {
    step_definition_uuid: string;
    extraction_json_path: string;
    operator: 'equals' | 'not_equals' | 'contains' | 'greater_than' | 'less_than';
    target_value: any;
}

export interface StopWorkflowCheckerStep {
    uuid: string;
    user_id: string;
    name: string;
    description: string;
    type: 'stop_checker';
    stop_conditions: StopWorkflowCondition[];
}

export type WorkflowStep = CustomLLMStep | CustomAgentStep | StopWorkflowCheckerStep;

export interface WorkflowWithDetails {
    uuid: string;
    user_id: string;
    name: string;
    description: string;
    is_active: boolean;
    trigger: TriggerModel | null;
    steps: WorkflowStep[];
    template_id: string | null;
    template_version: string | null;
    created_at: string;
    updated_at: string;
}

export const getWorkflows = async (): Promise<Workflow[]> => {
    try {
        const response = await fetch(`${API_URL}/workflows`);
        if (!response.ok) {
            console.error('Failed to fetch workflows. Status:', response.status);
            throw new Error('Failed to fetch workflows');
        }
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('An error occurred while fetching workflows:', error);
        return [];
    }
};

export const getWorkflowDetails = async (workflowId: string): Promise<WorkflowWithDetails | null> => {
    try {
        const response = await fetch(`${API_URL}/workflows/${workflowId}`);
        if (!response.ok) {
            console.error('Failed to fetch workflow details. Status:', response.status);
            throw new Error('Failed to fetch workflow details');
        }
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('An error occurred while fetching workflow details:', error);
        return null;
    }
};

export interface CreateWorkflowRequest {
    name: string;
    description: string;
}

export const createWorkflow = async (workflowData: CreateWorkflowRequest): Promise<Workflow | null> => {
    try {
        const response = await fetch(`${API_URL}/workflows`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(workflowData),
        });
        if (!response.ok) {
            console.error('Failed to create workflow. Status:', response.status);
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while creating the workflow:', error);
        return null;
    }
};

export const deleteWorkflow = async (workflowId: string): Promise<boolean> => {
    try {
        const response = await fetch(`${API_URL}/workflows/${workflowId}`, {
            method: 'DELETE',
        });
        if (!response.ok) {
            console.error('Failed to delete workflow. Status:', response.status);
            return false;
        }
        return true;
    } catch (error) {
        console.error('An error occurred while deleting the workflow:', error);
        return false;
    }
};

export const updateWorkflowDetails = async (
  workflowId: string,
  data: { name?: string; description?: string }
): Promise<Workflow | null> => {
  try {
    const response = await fetch(`${API_URL}/workflows/${workflowId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      console.error('Failed to update workflow details. Status:', response.status);
      return null;
    }
    return await response.json();
  } catch (error) {
    console.error('An error occurred while updating workflow details:', error);
    return null;
  }
};

export interface TriggerType {
    id: string;
    name: string;
    description: string;
    initial_data_description: string;
}

export interface LLMModel {
    id: string;
    name: string;
}

export interface Tool {
    id: string;
    name: string;
    description: string;
    server: string;
    input_schema: any;
}

export interface StepType {
    type: string;
    name: string;
    description: string;
}

export interface ChatMessage {
    role: 'user' | 'assistant' | 'tool';
    content: string;
    tool_calls?: any[];
    tool_call_id?: string;
}

export interface ChatRequest {
    conversation_id: string;
    messages: ChatMessage[];
}

export interface ChatStepResponse {
    conversation_id: string;
    messages: ChatMessage[];
    is_complete: boolean;
}

export const getAvailableTriggerTypes = async (): Promise<TriggerType[]> => {
    try {
        const response = await fetch(`${API_URL}/workflows/available-trigger-types`);
        if (!response.ok) {
            console.error('Failed to fetch trigger types. Status:', response.status);
            return [];
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while fetching trigger types:', error);
        return [];
    }
};

export const getAvailableLLMModels = async (): Promise<LLMModel[]> => {
    try {
        const response = await fetch(`${API_URL}/workflows/available-llm-models`);
        if (!response.ok) {
            console.error('Failed to fetch LLM models. Status:', response.status);
            return [];
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while fetching LLM models:', error);
        return [];
    }
};

export const getAvailableTools = async (): Promise<Tool[]> => {
    try {
        const response = await fetch(`${API_URL}/workflows/available-tools`);
        if (!response.ok) {
            console.error('Failed to fetch tools. Status:', response.status);
            return [];
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while fetching tools:', error);
        return [];
    }
};

export const getAvailableStepTypes = async (): Promise<StepType[]> => {
    try {
        const response = await fetch(`${API_URL}/workflows/available-step-types`);
        if (!response.ok) {
            console.error('Failed to fetch step types. Status:', response.status);
            return [];
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while fetching step types:', error);
        return [];
    }
};

export const addWorkflowStep = async (workflowId: string, stepType: string, name: string): Promise<WorkflowWithDetails | null> => {
    try {
        const response = await fetch(`${API_URL}/workflows/${workflowId}/steps`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ step_type: stepType, name }),
        });
        if (!response.ok) {
            console.error('Failed to add workflow step. Status:', response.status);
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while adding workflow step:', error);
        return null;
    }
}

export const runWorkflowAgentChatStep = async (
    workflowId: string, 
    request: ChatRequest,
    signal?: AbortSignal
): Promise<ChatStepResponse | 'aborted' | null> => {
    try {
        const response = await fetch(`${API_URL}/workflows/${workflowId}/chat/step`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(request),
            signal, // Pass the abort signal to fetch
        });
        if (!response.ok) {
            console.error('Failed to run chat step. Status:', response.status);
            const errorBody = await response.json();
            console.error('Error details:', errorBody);
            throw new Error(`Failed to run chat step: ${errorBody.detail}`);
        }
        return await response.json();
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Fetch aborted by user.');
            return 'aborted';
        }
        console.error('An error occurred during the chat step:', error);
        return null;
    }
};

export const updateWorkflowStep = async (step: WorkflowStep): Promise<WorkflowStep | null> => {
    try {
        const response = await fetch(`${API_URL}/workflows/steps/${step.uuid}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(step),
        });
        if (!response.ok) {
            console.error('Failed to update workflow step. Status:', response.status);
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while updating the workflow step:', error);
        return null;
    }
};

export const removeWorkflowStep = async (workflowId: string, stepId: string): Promise<boolean> => {
    try {
        const response = await fetch(`${API_URL}/workflows/${workflowId}/steps/${stepId}`, {
            method: 'DELETE',
        });
        return response.ok;
    } catch (error) {
        console.error('An error occurred while removing workflow step:', error);
        return false;
    }
}

export const reorderWorkflowSteps = async (workflowId: string, ordered_step_uuids: string[]): Promise<WorkflowWithDetails | null> => {
    try {
        const response = await fetch(`${API_URL}/workflows/${workflowId}/steps/reorder`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ordered_step_uuids }),
        });
        if (!response.ok) {
            console.error('Failed to reorder workflow steps. Status:', response.status);
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while reordering workflow steps:', error);
        return null;
    }
};

export const updateWorkflowStatus = async (
    workflowId: string, 
    isActive: boolean
): Promise<Workflow | null> => {
    try {
        const response = await fetch(`${API_URL}/workflows/${workflowId}/status`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ is_active: isActive }),
        });
        if (!response.ok) {
            console.error('Failed to update workflow status. Status:', response.status);
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while updating workflow status:', error);
        return null;
    }
};

export const setWorkflowTrigger = async (workflowId: string, triggerTypeId: string): Promise<WorkflowWithDetails | null> => {
    try {
        const response = await fetch(`${API_URL}/workflows/${workflowId}/trigger`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ trigger_type_id: triggerTypeId }),
        });
        if (!response.ok) {
            console.error('Failed to set workflow trigger. Status:', response.status);
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while setting workflow trigger:', error);
        return null;
    }
};

export const removeWorkflowTrigger = async (workflowId: string): Promise<WorkflowWithDetails | null> => {
    try {
        const response = await fetch(`${API_URL}/workflows/${workflowId}/trigger`, {
            method: 'DELETE',
        });
        if (!response.ok) {
            console.error('Failed to remove workflow trigger. Status:', response.status);
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while removing workflow trigger:', error);
        return null;
    }
};

export const updateWorkflowTrigger = async (
    workflowId: string, 
    filterRules: any
): Promise<WorkflowWithDetails | null> => {
    try {
        const url = `${API_URL}/workflows/${workflowId}/trigger`;
        const body = { filter_rules: filterRules };
        console.log('[workflows_api] Sending PUT request to:', url, 'with body:', JSON.stringify(body));

        const response = await fetch(url, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });

        console.log('[workflows_api] Received response with status:', response.status);

        if (!response.ok) {
            console.error('Failed to update workflow trigger. Status:', response.status, 'Response:', await response.text());
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('An error occurred while updating workflow trigger:', error);
        return null;
    }
}; 