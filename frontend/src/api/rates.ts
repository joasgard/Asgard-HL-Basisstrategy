import apiClient from './client';

export interface RatesResponse {
  asset: string;
  net_apy: number;
  funding_rate: number;
  net_carry: number;
  protocol: string;
  leverage: number;
}

export const ratesApi = {
  async getCurrent(leverage: number = 3.0): Promise<RatesResponse[]> {
    const response = await apiClient.get('/rates', {
      params: { leverage },
    });
    return response.data;
  },

  async getBestOpportunity(leverage: number = 3.0): Promise<RatesResponse | null> {
    const rates = await this.getCurrent(leverage);
    return rates.length > 0 ? rates[0] : null;
  },
};

export default ratesApi;
