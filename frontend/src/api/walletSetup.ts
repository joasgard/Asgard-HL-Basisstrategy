import apiClient from './client';

export interface WalletStatus {
  user_id: string;
  wallets: Array<{
    id: string;
    address: string;
    chain_type: string;
  }>;
  has_ethereum: boolean;
  has_solana: boolean;
}

export interface WalletSetupResponse {
  success: boolean;
  message: string;
  solana_address?: string;
  ethereum_address?: string;
}

export const walletSetupApi = {
  async getWalletStatus(): Promise<WalletStatus> {
    const response = await apiClient.get('/wallet-setup/wallet-status');
    return response.data;
  },

  async ensureWallets(): Promise<WalletSetupResponse> {
    const response = await apiClient.post('/wallet-setup/ensure-wallets');
    return response.data;
  },
};

export default walletSetupApi;
