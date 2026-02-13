import { apiClient } from './client';

export interface StrategyConfig {
  enabled: boolean;
  assets: string[];
  protocols: string[] | null;
  min_carry_apy: number;
  min_funding_rate_8hr: number;
  max_funding_volatility: number;
  max_position_pct: number;
  max_concurrent_positions: number;
  max_leverage: number;
  min_exit_carry_apy: number;
  take_profit_pct: number | null;
  stop_loss_pct: number;
  auto_reopen: boolean;
  cooldown_minutes: number;
  version: number;
  is_default: boolean;
}

export interface StrategyConfigUpdate {
  enabled?: boolean;
  min_carry_apy?: number;
  min_funding_rate_8hr?: number;
  max_funding_volatility?: number;
  max_position_pct?: number;
  max_concurrent_positions?: number;
  max_leverage?: number;
  min_exit_carry_apy?: number;
  take_profit_pct?: number | null;
  stop_loss_pct?: number;
  auto_reopen?: boolean;
  cooldown_minutes?: number;
  version: number;
}

export interface RiskStatus {
  bot_status: 'active' | 'paused' | 'inactive';
  paused_reason: string | null;
  drawdown_pct: number;
  peak_balance_usd: number;
  daily_trades: number;
  daily_trade_limit: number;
  consecutive_failures: number;
  last_failure_reason: string | null;
}

export interface CloseAllResponse {
  success: boolean;
  message: string;
  positions_closed: number;
  job_ids: string[];
}

export const strategyApi = {
  get: async (): Promise<StrategyConfig> => {
    const { data } = await apiClient.get('/strategy');
    return data;
  },

  update: async (config: StrategyConfigUpdate): Promise<StrategyConfig> => {
    const { data } = await apiClient.put('/strategy', config);
    return data;
  },

  pause: async (): Promise<{ success: boolean; message: string }> => {
    const { data } = await apiClient.post('/strategy/pause');
    return data;
  },

  resume: async (): Promise<{ success: boolean; message: string }> => {
    const { data } = await apiClient.post('/strategy/resume');
    return data;
  },

  getRiskStatus: async (): Promise<RiskStatus> => {
    const { data } = await apiClient.get('/strategy/risk-status');
    return data;
  },

  closeAllPositions: async (): Promise<CloseAllResponse> => {
    const { data } = await apiClient.post('/positions/close-all');
    return data;
  },
};
