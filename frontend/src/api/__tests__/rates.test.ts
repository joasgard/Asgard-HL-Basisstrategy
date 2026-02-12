import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ratesApi } from '../rates';
import apiClient from '../client';

vi.mock('../client', () => ({
  default: {
    get: vi.fn(),
  },
}));

describe('ratesApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockRatesResponse = {
    asgard: { kamino: 8.5, drift: 5.2 },
    asgard_details: { lending_apy: 25.5, borrowing_apy: 10.2, net_apy: 15.3 },
    hyperliquid: { funding_rate: -0.0025, predicted: -0.003, annualized: -3.0 },
    combined: { kamino: 18.5, drift: 15.2 },
    leverage: 3.0,
  };

  it('should get current rates', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: mockRatesResponse });

    const result = await ratesApi.getCurrent();

    expect(apiClient.get).toHaveBeenCalledWith('/rates', { params: { leverage: 3.0 } });
    expect(result).toEqual(mockRatesResponse);
  });

  it('should get current rates with custom leverage', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: mockRatesResponse });

    const result = await ratesApi.getCurrent(4.0);

    expect(apiClient.get).toHaveBeenCalledWith('/rates', { params: { leverage: 4.0 } });
    expect(result).toEqual(mockRatesResponse);
  });

  it('should get simple rates', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: mockRatesResponse });

    const result = await ratesApi.getSimple();

    expect(apiClient.get).toHaveBeenCalledWith('/rates/simple');
    expect(result).toEqual(mockRatesResponse);
  });
});
