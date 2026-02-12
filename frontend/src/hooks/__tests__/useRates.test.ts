import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useRates } from '../useRates';
import * as ratesApi from '../../api/rates';

vi.mock('../../api/rates', () => ({
  ratesApi: {
    getCurrent: vi.fn(),
  },
}));

const mockStoreState = {
  rates: null,
  historicalRates: [],
  isLoading: false,
  error: null,
  lastUpdated: null,
  setRates: vi.fn(),
  setHistoricalRates: vi.fn(),
  setLoading: vi.fn(),
  setError: vi.fn(),
  getNetApyAtLeverage: vi.fn(() => 0),
};

vi.mock('../../stores', () => ({
  useRatesStore: (selector?: (s: Record<string, unknown>) => unknown) => {
    if (selector) return selector(mockStoreState);
    return mockStoreState;
  },
  useUIStore: () => ({
    addToast: vi.fn(),
  }),
}));

describe('useRates', () => {
  const mockRatesResponse = {
    asgard: { kamino: 8.5, drift: 5.2 },
    asgard_details: { lending_apy: 25.5, borrowing_apy: 10.2, net_apy: 15.3 },
    hyperliquid: { funding_rate: -0.0025, predicted: -0.003, annualized: -3.0 },
    combined: { kamino: 18.5, drift: 15.2 },
    leverage: 3.0,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should return initial state', () => {
    const { result } = renderHook(() => useRates());

    expect(result.current.rates).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('should fetch rates successfully', async () => {
    (ratesApi.ratesApi.getCurrent as ReturnType<typeof vi.fn>).mockResolvedValue(mockRatesResponse);

    const { result } = renderHook(() => useRates());

    await result.current.fetchRates();

    await waitFor(() => {
      expect(ratesApi.ratesApi.getCurrent).toHaveBeenCalled();
      expect(mockStoreState.setRates).toHaveBeenCalled();
    });
  });

  it('should handle fetch rates error', async () => {
    (ratesApi.ratesApi.getCurrent as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useRates());

    await result.current.fetchRates();

    await waitFor(() => {
      expect(ratesApi.ratesApi.getCurrent).toHaveBeenCalled();
      expect(mockStoreState.setError).toHaveBeenCalledWith('Network error');
    });
  });
});
