import { apiClient } from './client';

export interface FundingJobResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface FundingJobStatus {
  job_id: string;
  direction: 'deposit' | 'withdraw';
  status: 'pending' | 'running' | 'completed' | 'failed';
  amount_usdc: number;
  error: string | null;
  approve_tx_hash: string | null;
  bridge_tx_hash: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export const fundingApi = {
  /** Bridge USDC from Arbitrum to Hyperliquid. */
  deposit: async (amountUsdc: number): Promise<FundingJobResponse> => {
    const { data } = await apiClient.post('/funding/deposit', { amount_usdc: amountUsdc });
    return data;
  },

  /** Withdraw USDC from Hyperliquid to Arbitrum. */
  withdraw: async (amountUsdc: number): Promise<FundingJobResponse> => {
    const { data } = await apiClient.post('/funding/withdraw', { amount_usdc: amountUsdc });
    return data;
  },

  /** Poll job status. */
  getJobStatus: async (jobId: string): Promise<FundingJobStatus> => {
    const { data } = await apiClient.get(`/funding/jobs/${jobId}`);
    return data;
  },

  /** Get deposit/withdrawal history. */
  getHistory: async (): Promise<FundingJobStatus[]> => {
    const { data } = await apiClient.get('/funding/history');
    return data;
  },
};
