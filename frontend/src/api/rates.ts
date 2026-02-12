import apiClient from './client';

export interface AsgardDetails {
  base_lending_apy: number;   // Base lending rate (no leverage)
  lending_apy: number;        // Leveraged lending rate
  base_borrowing_apy: number; // Base borrow rate (no leverage)
  borrowing_apy: number;      // Leveraged borrow cost
  net_apy: number;            // Net APY on long leg
}

export interface HyperliquidRates {
  funding_rate: number;      // Hourly % (e.g., -0.0025)
  predicted: number;          // Predicted hourly %
  base_annualized: number;   // Annualized % (no leverage)
  annualized: number;         // Annualized % at leverage
}

export interface RatesResponse {
  asgard: Record<string, number>;           // protocol -> net APY %
  asgard_details: AsgardDetails | null;     // Best protocol breakdown
  hyperliquid: HyperliquidRates;
  combined: Record<string, number>;          // protocol -> combined APY %
  leverage: number;
}

export const ratesApi = {
  async getCurrent(leverage: number = 3.0): Promise<RatesResponse> {
    const response = await apiClient.get('/rates', {
      params: { leverage },
    });
    return response.data;
  },

  async getSimple(): Promise<RatesResponse> {
    const response = await apiClient.get('/rates/simple');
    return response.data;
  },
};

export default ratesApi;
