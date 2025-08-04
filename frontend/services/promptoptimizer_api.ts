
import { API_URL, jsonApiFetch } from './api';

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
  name: string;
  description: string | null;
  user_id: string;
  data_source_config: {
    tool: string;
    params: Record<string, any>;
  };
  field_mapping_config: {
    input_field: string;
    ground_truth_field: string;
    ground_truth_transform?: string;
  };
  cached_data: Record<string, any>[];
  created_at: string;
  updated_at: string;
  status: 'processing' | 'completed' | 'failed';
  processing_error: string | null;
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
      ground_truth_transform?: string;
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
    ground_truth_transform?: string;
  };
}


// --- API Functions ---

export const listDataSources = async (): Promise<DataSource[]> => {
  return await jsonApiFetch(`${API_URL}/evaluation/data-sources`);
};

export const getDataSourceConfigSchema = async (sourceId: string): Promise<Record<string, any>> => {
    return await jsonApiFetch(`${API_URL}/evaluation/data-sources/${sourceId}/config-schema`);
};

export const fetchDataSourceSample = async (sourceId: string, config: Record<string, any>): Promise<Record<string, any>> => {
    return await jsonApiFetch(`${API_URL}/evaluation/data-sources/${sourceId}/sample`, {
        method: 'POST',
        body: JSON.stringify({ config }),
    });
};

export const listEvaluationTemplates = async (): Promise<EvaluationTemplate[]> => {
    return await jsonApiFetch(`${API_URL}/evaluation/templates`);
};

export const getEvaluationTemplate = async (templateId: string): Promise<EvaluationTemplate> => {
    const template = await jsonApiFetch(`${API_URL}/evaluation/templates/${templateId}`);
    if (!template) {
        throw new Error("Template not found");
    }
    return template;
}

// --- Evaluation Run Endpoints ---

export interface EvaluationRun {
    uuid: string;
    user_id: string;
    template_uuid: string;
    workflow_step_uuid: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    summary_report: Record<string, any> | null;
    detailed_results: Record<string, any> | null;
    started_at: string | null;
    finished_at: string | null;
    created_at: string;
}

export async function runEvaluation(templateId: string, prompt: string, model: string): Promise<EvaluationRun> {
    return await jsonApiFetch(`/api/evaluation/templates/${templateId}/run`, {
        method: 'POST',
        body: JSON.stringify({
            original_prompt: prompt,
            original_model: model
        }),
    });
}

export async function getEvaluationRun(runId: string): Promise<EvaluationRun> {
    const run = await jsonApiFetch(`/api/evaluation/runs/${runId}`);
    return run;
}

export const createEvaluationTemplate = async (templateData: EvaluationTemplateCreate): Promise<EvaluationTemplate> => {
    return await jsonApiFetch(`${API_URL}/evaluation/templates`, {
        method: 'POST',
        body: JSON.stringify(templateData),
    });
};

export const updateEvaluationTemplate = async (templateId: string, templateData: EvaluationTemplateUpdate): Promise<EvaluationTemplate> => {
    return await jsonApiFetch(`${API_URL}/evaluation/templates/${templateId}`, {
        method: 'PUT',
        body: JSON.stringify(templateData),
    });
}; 