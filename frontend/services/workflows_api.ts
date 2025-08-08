import { apiFetch, jsonApiFetch } from './api';

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
    trigger_prompt?: string;
    trigger_model?: string;
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

export interface StopWorkflowCheckerStep {
    uuid: string;
    user_id: string;
    name: string;
    description: string;
    type: 'stop_checker';
    step_to_check_uuid: string | null;
    check_mode: 'stop_if_output_contains' | 'continue_if_output_contains';
    match_values: string[];
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

export interface Template {
    id: string;
    name: string;
    description: string;
}

export interface WorkflowFromTemplateResponse {
    workflow: Workflow;
    workflow_start_message?: string;
}

export const getWorkflows = async (): Promise<Workflow[]> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows`);
    } catch (error) {
        console.error('An error occurred while fetching workflows:', error);
        return [];
    }
};

export const getWorkflowDetails = async (workflowId: string): Promise<WorkflowWithDetails | null> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/${workflowId}`);
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
        return await jsonApiFetch(`${API_URL}/workflows`, {
            method: 'POST',
            body: JSON.stringify(workflowData),
        });
    } catch (error) {
        console.error('An error occurred while creating the workflow:', error);
        return null;
    }
};

export const getWorkflowTemplates = async (): Promise<Template[]> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/templates`);
    } catch (error) {
        console.error('Error fetching workflow templates:', error);
        return [];
    }
};

export const createWorkflowFromTemplate = async (templateId: string): Promise<WorkflowFromTemplateResponse | null> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/from-template`, {
            method: 'POST',
            body: JSON.stringify({ template_id: templateId }),
        });
    } catch (error) {
        console.error('Error creating workflow from template:', error);
        return null;
    }
};

export const deleteWorkflow = async (workflowId: string): Promise<boolean> => {
    try {
        await apiFetch(`${API_URL}/workflows/${workflowId}`, {
            method: 'DELETE',
        });
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
    return await jsonApiFetch(`${API_URL}/workflows/${workflowId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  } catch (error) {
    console.error('An error occurred while updating workflow details:', error);
    return null;
  }
};

export const exportWorkflow = async (workflowId: string): Promise<void> => {
    try {
        const response = await apiFetch(`${API_URL}/workflows/${workflowId}/export`);
        const blob = await response.blob();

        // Extract filename from Content-Disposition header
        const contentDisposition = response.headers.get('content-disposition');
        console.log('[exportWorkflow] Received Content-Disposition header:', contentDisposition);

        let filename = 'workflow.json'; // default filename
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="([^"]+)"/);
            if (filenameMatch && filenameMatch.length > 1) {
                filename = filenameMatch[1];
            }
        }
        console.log('[exportWorkflow] Parsed filename:', filename);

        // Create a temporary link to trigger the download
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error('An error occurred while exporting the workflow:', error);
        // Handle error appropriately in the UI
    }
};

export const importWorkflow = async (file: File): Promise<Workflow | null> => {
    const formData = new FormData();
    formData.append('file', file);

    try {
        return await jsonApiFetch(`${API_URL}/workflows/import`, {
            method: 'POST',
            body: formData,
        });
    } catch (error) {
        console.error('An error occurred while importing the workflow:', error);
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
    human_input_required?: {
        type: string;
        tool_call_id: string;
        data: any;
    } | null;
}

export interface HumanInputSubmission {
    conversation_id: string;
    messages: ChatMessage[];
    tool_call_id: string;
    user_input: any;
}

export const getAvailableTriggerTypes = async (): Promise<TriggerType[]> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/available-trigger-types`);
    } catch (error) {
        console.error('An error occurred while fetching trigger types:', error);
        return [];
    }
};

export const getAvailableLLMModels = async (): Promise<LLMModel[]> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/available-llm-models`);
    } catch (error) {
        console.error('An error occurred while fetching LLM models:', error);
        return [];
    }
};

export const getAvailableTools = async (): Promise<Tool[]> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/available-tools`);
    } catch (error) {
        console.error('An error occurred while fetching tools:', error);
        return [];
    }
};

export const getAvailableStepTypes = async (): Promise<StepType[]> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/available-step-types`);
    } catch (error) {
        console.error('An error occurred while fetching step types:', error);
        return [];
    }
};

export const addWorkflowStep = async (workflowId: string, stepType: string, name: string): Promise<WorkflowWithDetails | null> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/${workflowId}/steps`, {
            method: 'POST',
            body: JSON.stringify({ step_type: stepType, name }),
        });
    } catch (error) {
        console.error('An error occurred while adding workflow step:', error);
        return null;
    }
}

export const runWorkflowAgentChatStep = async (
    workflowId: string, 
    request: ChatRequest,
    signal?: AbortSignal
): Promise<ChatStepResponse | 'aborted'> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/${workflowId}/chat/step`, {
            method: 'POST',
            body: JSON.stringify(request),
            signal, // Pass the abort signal to fetch
        });
    } catch (error: any) {
        if (error.name === 'AbortError') {
            console.log('Fetch aborted by user.');
            return 'aborted';
        }
        console.error('An error occurred during the chat step:', error);
        // Re-throw the error so the component can handle it
        throw error;
    }
};

export const submitHumanInput = async (
    workflowId: string,
    submission: HumanInputSubmission,
    signal?: AbortSignal
): Promise<ChatStepResponse | 'aborted'> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/${workflowId}/chat/submit_human_input`, {
            method: 'POST',
            body: JSON.stringify(submission),
            signal,
        });
    } catch (error: any) {
        if (error.name === 'AbortError') {
            return 'aborted';
        }
        console.error('An error occurred while submitting human input:', error);
        // Re-throw the error so the component can handle it
        throw error;
    }
};

export const updateWorkflowStep = async (step: WorkflowStep): Promise<WorkflowStep | null> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/steps/${step.uuid}`, {
            method: 'PUT',
            body: JSON.stringify(step),
        });
    } catch (error) {
        console.error('An error occurred while updating the workflow step:', error);
        return null;
    }
};

export const removeWorkflowStep = async (workflowId: string, stepId: string): Promise<boolean> => {
    try {
        await apiFetch(`${API_URL}/workflows/${workflowId}/steps/${stepId}`, {
            method: 'DELETE',
        });
        return true;
    } catch (error) {
        console.error('An error occurred while removing workflow step:', error);
        return false;
    }
}

export const reorderWorkflowSteps = async (workflowId: string, ordered_step_uuids: string[]): Promise<WorkflowWithDetails | null> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/${workflowId}/steps/reorder`, {
            method: 'POST',
            body: JSON.stringify({ ordered_step_uuids }),
        });
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
        return await jsonApiFetch(`${API_URL}/workflows/${workflowId}/status`, {
            method: 'PUT',
            body: JSON.stringify({ is_active: isActive }),
        });
    } catch (error) {
        console.error('An error occurred while updating workflow status:', error);
        return null;
    }
};

export const setWorkflowTrigger = async (workflowId: string, triggerTypeId: string): Promise<WorkflowWithDetails | null> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/${workflowId}/trigger`, {
            method: 'POST',
            body: JSON.stringify({ trigger_type_id: triggerTypeId }),
        });
    } catch (error) {
        console.error('An error occurred while setting workflow trigger:', error);
        return null;
    }
};

export const removeWorkflowTrigger = async (workflowId: string): Promise<WorkflowWithDetails | null> => {
    try {
        return await jsonApiFetch(`${API_URL}/workflows/${workflowId}/trigger`, {
            method: 'DELETE',
        });
    } catch (error) {
        console.error('An error occurred while removing workflow trigger:', error);
        return null;
    }
};

export const updateWorkflowTrigger = async (
    workflowId: string, 
    triggerData: {
      filter_rules?: any;
      trigger_prompt?: string;
      trigger_model?: string;
    }
): Promise<WorkflowWithDetails | null> => {
    try {
        const url = `${API_URL}/workflows/${workflowId}/trigger`;
        console.log('[workflows_api] Sending PUT request to:', url, 'with body:', JSON.stringify(triggerData));

        const data = await jsonApiFetch(url, {
            method: 'PUT',
            body: JSON.stringify(triggerData),
        });

        console.log('[workflows_api] Received response with status: 200');
        return data;
    } catch (error) {
        console.error('An error occurred while updating workflow trigger:', error);
        return null;
    }
}; 