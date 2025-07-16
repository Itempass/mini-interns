
import { API_URL } from './api';

// --- Type Definitions ---

export interface DataSource {
  id: string;
  name: string;
}

export interface EvaluationTemplateLight {
  uuid: string;
  user_id: string;
  name: string;
  description?: string;
  updated_at: string;
}

export interface EvaluationTemplate {
  uuid: string;
  user_id: string;
  name: string;
  description?: string;
  data_source_config: {
    tool: string;
    params: Record<string, any>;
  };
  field_mapping_config: {
    input_field: string;
    ground_truth_field: string;
  };
  cached_data: any[];
  created_at: string;
  updated_at: string;
}

export interface EvaluationTemplateCreate {
    name: string;
    description?: string;
    data_source_config: {
      tool: string;
      params: Record<string, any>;
    };
    field_mapping_config: {
      input_field: string;
      ground_truth_field: string;
    };
}

// Used for updating - data_source_config is optional.
export interface EvaluationTemplateUpdate {
  name: string;
  description?: string;
  data_source_config?: {
    tool: string;
    params: Record<string, any>;
  };
  field_mapping_config: {
    input_field: string;
    ground_truth_field: string;
  };
}


// --- API Functions ---

export const listDataSources = async (): Promise<DataSource[]> => {
  const response = await fetch(`${API_URL}/evaluation/data-sources`);
  if (!response.ok) {
    throw new Error('Failed to fetch data sources');
  }
  return response.json();
};

export const getDataSourceConfigSchema = async (sourceId: string): Promise<Record<string, any>> => {
    const response = await fetch(`${API_URL}/evaluation/data-sources/${sourceId}/config-schema`);
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch config schema');
    }
    return response.json();
};

export const fetchDataSourceSample = async (sourceId: string, config: Record<string, any>): Promise<Record<string, any>> => {
    const response = await fetch(`${API_URL}/evaluation/data-sources/${sourceId}/sample`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ config }),
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch sample data');
    }
    return response.json();
};

export const listEvaluationTemplates = async (): Promise<EvaluationTemplate[]> => {
    const response = await fetch(`${API_URL}/evaluation/templates`);
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch evaluation templates');
    }
    return response.json();
};

export const getEvaluationTemplate = async (templateId: string): Promise<EvaluationTemplate> => {
    const response = await fetch(`${API_URL}/evaluation/templates/${templateId}`);
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch evaluation template');
    }
    return response.json();
};

export const createEvaluationTemplate = async (templateData: EvaluationTemplateCreate): Promise<EvaluationTemplate> => {
    const response = await fetch(`${API_URL}/evaluation/templates`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(templateData),
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create evaluation template');
    }
    return response.json();
};

export const updateEvaluationTemplate = async (templateId: string, templateData: EvaluationTemplateUpdate): Promise<EvaluationTemplate> => {
    const response = await fetch(`${API_URL}/evaluation/templates/${templateId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(templateData),
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to update evaluation template');
    }
    return response.json();
}; 