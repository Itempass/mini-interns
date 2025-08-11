
import { API_URL, jsonApiFetch, apiFetch } from './api';

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

export interface ThreadListFilters {
  folder_names?: string[];
  filter_by_labels?: string[];
}

export interface ThreadListItem {
  id: string; // message_id
  subject: string;
  from: string;
  to: string;
  date: string;
  folders: string[];
  labels: string[];
}

export interface ThreadListResponse {
  items: ThreadListItem[];
  total: number;
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

export const listThreads = async (
  sourceId: string,
  filters: ThreadListFilters,
  page: number,
  pageSize: number
): Promise<ThreadListResponse> => {
  return await jsonApiFetch(`${API_URL}/evaluation/data-sources/${sourceId}/threads/list`, {
    method: 'POST',
    body: JSON.stringify({ filters, page, page_size: pageSize }),
  });
};

export const exportThreadsDataset = async (
  sourceId: string,
  selectedIds: string[],
  opts?: { useUids?: boolean }
): Promise<Blob> => {
  const response = await apiFetch(`${API_URL}/evaluation/data-sources/${sourceId}/export`, {
    method: 'POST',
    body: JSON.stringify(opts?.useUids ? { selected_uids: selectedIds } : { selected_ids: selectedIds }),
  });
  return await response.blob();
};

export const collectThreadIds = async (
  sourceId: string,
  filters: ThreadListFilters,
  limit: number
): Promise<string[]> => {
  const res = await jsonApiFetch(`${API_URL}/evaluation/data-sources/${sourceId}/threads/collect-ids`, {
    method: 'POST',
    body: JSON.stringify({ filters, limit }),
  });
  return res.ids || [];
};

export const startExportJob = async (
  sourceId: string,
  selectedIds: string[]
): Promise<{ job_id: string; status: string }> => {
  return await jsonApiFetch(`${API_URL}/evaluation/data-sources/${sourceId}/export/jobs`, {
    method: 'POST',
    body: JSON.stringify({ selected_ids: selectedIds }),
  });
};

export const getExportJobStatus = async (
  jobId: string
): Promise<{ job_id: string; status: 'processing' | 'completed' | 'failed' }> => {
  return await jsonApiFetch(`${API_URL}/evaluation/data-sources/export/jobs/${jobId}`);
};

export const getExportJobProgress = async (
  jobId: string
): Promise<{ job_id: string; status: 'processing' | 'completed' | 'failed'; total: number; completed: number }> => {
  return await jsonApiFetch(`${API_URL}/evaluation/data-sources/export/jobs/${jobId}/progress`);
};

export const downloadExportJob = async (
  jobId: string
): Promise<Blob> => {
  const response = await apiFetch(`${API_URL}/evaluation/data-sources/export/jobs/${jobId}/download`);
  return await response.blob();
}; 