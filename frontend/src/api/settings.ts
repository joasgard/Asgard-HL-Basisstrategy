import apiClient from './client';

export interface StrategySettings {
  default_leverage: number;
  max_position_size: number;
  min_position_size: number;
  max_positions_per_asset: number;
  min_opportunity_apy: number;
  max_funding_volatility: number;
  price_deviation_threshold: number;
  delta_drift_threshold: number;
  enable_auto_exit: boolean;
  enable_circuit_breakers: boolean;
}

export const settingsApi = {
  async get(): Promise<StrategySettings> {
    const response = await apiClient.get('/settings');
    return response.data;
  },

  async update(settings: Partial<StrategySettings>): Promise<StrategySettings> {
    const response = await apiClient.post('/settings', settings);
    return response.data;
  },

  async reset(): Promise<StrategySettings> {
    const response = await apiClient.post('/settings/reset');
    return response.data;
  },
};

export default settingsApi;
