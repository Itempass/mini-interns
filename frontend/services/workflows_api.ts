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

export interface TriggerType {
    id: string;
    name: string;
    description: string;
    initial_data_description: string;
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

export const setWorkflowTrigger = async (workflowId: string, triggerTypeId: string): Promise<Workflow | null> => {
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

export const removeWorkflowTrigger = async (workflowId: string): Promise<Workflow | null> => {
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