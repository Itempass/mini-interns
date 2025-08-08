import { jsonApiFetch, apiFetch, API_URL } from './api';

export interface VectorDatabase {
  uuid: string;
  user_id: string;
  name: string;
  type: 'internal' | 'external';
  provider: string;
  settings: Record<string, any>;
  status?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface AvailableDbConfig {
    settings: Record<string, any>;
    type: 'internal' | 'external';
};

export const getAvailableProviders = async (): Promise<Record<string, AvailableDbConfig>> => {
    return jsonApiFetch(`${API_URL}/rag/providers`);
};

export const createVectorDatabase = async (dbConfig: Omit<VectorDatabase, 'uuid' | 'user_id' | 'created_at' | 'updated_at'>): Promise<VectorDatabase> => {
  return jsonApiFetch(`${API_URL}/rag/vector-databases`, {
    method: 'POST',
    body: JSON.stringify(dbConfig),
  });
};

export const getVectorDatabase = async (uuid: string): Promise<VectorDatabase> => {
  return jsonApiFetch(`${API_URL}/rag/vector-databases/${uuid}`);
};

export const listVectorDatabases = async (): Promise<VectorDatabase[]> => {
  return jsonApiFetch(`${API_URL}/rag/vector-databases`);
};

export const updateVectorDatabase = async (uuid: string, dbConfig: Partial<VectorDatabase>): Promise<VectorDatabase> => {
  return jsonApiFetch(`${API_URL}/rag/vector-databases/${uuid}`, {
    method: 'PUT',
    body: JSON.stringify(dbConfig),
  });
};

export const deleteVectorDatabase = async (uuid: string): Promise<void> => {
    await apiFetch(`${API_URL}/rag/vector-databases/${uuid}`, {
        method: 'DELETE',
    });
    return;
}; 