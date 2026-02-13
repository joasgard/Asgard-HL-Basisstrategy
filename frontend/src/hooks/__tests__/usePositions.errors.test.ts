import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { usePositions } from '../usePositions';
import * as positionsApi from '../../api/positions';

vi.mock('../../api/positions', () => ({
  positionsApi: {
    list: vi.fn(),
    open: vi.fn(),
    close: vi.fn(),
    get: vi.fn(),
    getJobStatus: vi.fn(),
  },
}));

vi.mock('@privy-io/react-auth', () => ({
  usePrivy: () => ({ authenticated: true }),
}));

vi.mock('../../api/client', () => ({
  formatErrorForDisplay: (err: unknown) => ({
    title: 'Error',
    message: (err as Error)?.message || 'Unknown error',
    code: 'GEN-0001',
  }),
}));

const mockStore = {
  positions: [],
  isLoading: false,
  error: null,
  selectedPosition: null,
  totalPnl: 0,
  totalValue: 0,
  openPositionsCount: 0,
  setPositions: vi.fn(),
  addPosition: vi.fn(),
  updatePosition: vi.fn(),
  removePosition: vi.fn(),
  setLoading: vi.fn(),
  setError: vi.fn(),
  selectPosition: vi.fn(),
};

vi.mock('../../stores', () => ({
  usePositionsStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    return selector ? selector(mockStore as unknown as Record<string, unknown>) : mockStore;
  },
  useUIStore: () => ({
    addToast: vi.fn(),
    addErrorToast: vi.fn(),
  }),
}));

describe('usePositions - Error Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should handle fetch error', async () => {
    (positionsApi.positionsApi.list as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Network error')
    );

    const { result } = renderHook(() => usePositions());
    await result.current.fetchPositions();

    await waitFor(() => {
      expect(positionsApi.positionsApi.list).toHaveBeenCalled();
    });
  });

  it('should handle open position error', async () => {
    (positionsApi.positionsApi.open as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Insufficient funds')
    );

    const { result } = renderHook(() => usePositions());
    
    await expect(result.current.openPosition('SOL', 3.0, 5000)).rejects.toThrow();
  });

  it('should handle close position error', async () => {
    (positionsApi.positionsApi.close as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Position not found')
    );

    const { result } = renderHook(() => usePositions());
    
    await expect(result.current.closePosition('pos_1')).rejects.toThrow();
  });

  it('should handle refresh position error', async () => {
    (positionsApi.positionsApi.get as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Position not found')
    );

    const { result } = renderHook(() => usePositions());
    
    await expect(result.current.refreshPosition('pos_1')).rejects.toThrow();
  });

  it('should handle successful position open', async () => {
    (positionsApi.positionsApi.open as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: 'job_123',
    });

    const { result } = renderHook(() => usePositions());
    
    await result.current.openPosition('SOL', 3.0, 5000);

    await waitFor(() => {
      expect(positionsApi.positionsApi.open).toHaveBeenCalledWith({
        asset: 'SOL',
        leverage: 3.0,
        size_usd: 5000,
      });
    });
  });

  it('should handle successful position close', async () => {
    (positionsApi.positionsApi.close as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: 'job_456',
    });

    const { result } = renderHook(() => usePositions());
    
    await result.current.closePosition('pos_1');

    await waitFor(() => {
      expect(positionsApi.positionsApi.close).toHaveBeenCalledWith('pos_1');
    });
  });
});
