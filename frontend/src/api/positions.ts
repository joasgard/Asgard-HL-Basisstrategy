import apiClient from './client';

export interface Position {
  id: string;
  asset: string;
  status: 'open' | 'closing' | 'closed';
  leverage: number;
  size_usd: number;
  pnl_usd: number;
  pnl_percent: number;
  entry_price: number;
  current_price: number;
  health_factor: number;
  created_at: string;
  asgard_pda?: string;
  hyperliquid_address?: string;
}

export interface JobStatus {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  position_id?: string;
  error?: string;
  error_code?: string;
  error_stage?: string;
  created_at?: string;
  completed_at?: string;
  params?: {
    asset?: string;
    leverage?: number;
    size_usd?: number;
    action?: 'close';
  };
}

export interface OpenPositionRequest {
  asset: string;
  leverage: number;
  size_usd: number;
}

export const positionsApi = {
  async list(): Promise<Position[]> {
    const response = await apiClient.get('/positions');
    return response.data;
  },

  async get(positionId: string): Promise<Position> {
    const response = await apiClient.get(`/positions/${positionId}`);
    return response.data;
  },

  async open(request: OpenPositionRequest): Promise<{ job_id: string }> {
    const response = await apiClient.post('/positions/open', request);
    return response.data;
  },

  async close(positionId: string): Promise<{ job_id: string }> {
    const response = await apiClient.post(`/positions/${positionId}/close`);
    return response.data;
  },

  async getJobStatus(jobId: string): Promise<JobStatus> {
    const response = await apiClient.get(`/positions/jobs/${jobId}`);
    return response.data;
  },
};

export default positionsApi;
