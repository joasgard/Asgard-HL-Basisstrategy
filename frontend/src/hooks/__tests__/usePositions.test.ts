import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { usePositions } from '../usePositions';
import * as positionsApi from '../../api/positions';

// Mock the API
vi.mock('../../api/positions', () => ({
  positionsApi: {
    list: vi.fn(),
    open: vi.fn(),
    close: vi.fn(),
    get: vi.fn(),
    getJobStatus: vi.fn(),
  },
}));

// Mock the stores
vi.mock('../../stores', () => ({
  usePositionsStore: (selector?: (state: unknown) => unknown) => {
    const store = {
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
    return selector ? selector(store) : store;
  },
  useUIStore: () => ({
    addToast: vi.fn(),
  }),
}));

describe('usePositions', () => {
  const mockPosition = {
    id: 'pos_1',
    asset: 'SOL',
    status: 'open',
    leverage: 3.0,
    size_usd: 5000,
    pnl_usd: 100,
    pnl_percent: 2,
    entry_price: 150,
    current_price: 153,
    health_factor: 0.25,
    created_at: '2026-02-10T00:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should return actions', () => {
    const { result } = renderHook(() => usePositions());

    expect(typeof result.current.fetchPositions).toBe('function');
    expect(typeof result.current.openPosition).toBe('function');
    expect(typeof result.current.closePosition).toBe('function');
    expect(typeof result.current.refreshPosition).toBe('function');
    expect(typeof result.current.selectPosition).toBe('function');
  });

  it('should fetch positions successfully', async () => {
    const mockPositions = [mockPosition];
    (positionsApi.positionsApi.list as ReturnType<typeof vi.fn>).mockResolvedValue(mockPositions);

    const { result } = renderHook(() => usePositions());
    
    await result.current.fetchPositions();

    await waitFor(() => {
      expect(positionsApi.positionsApi.list).toHaveBeenCalled();
    });
  });

  it('should handle fetch positions error', async () => {
    (positionsApi.positionsApi.list as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => usePositions());
    
    await result.current.fetchPositions();

    await waitFor(() => {
      expect(positionsApi.positionsApi.list).toHaveBeenCalled();
    });
  });

  it('should open position successfully', async () => {
    const mockResponse = { job_id: 'job_123' };
    (positionsApi.positionsApi.open as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);
    (positionsApi.positionsApi.getJobStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'completed',
      position_id: 'pos_new',
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

  it('should close position successfully', async () => {
    const mockResponse = { job_id: 'job_456' };
    (positionsApi.positionsApi.close as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);
    (positionsApi.positionsApi.getJobStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'completed',
    });

    const { result } = renderHook(() => usePositions());
    
    await result.current.closePosition('pos_1');

    await waitFor(() => {
      expect(positionsApi.positionsApi.close).toHaveBeenCalledWith('pos_1');
    });
  });

  it('should refresh position', async () => {
    (positionsApi.positionsApi.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockPosition);

    const { result } = renderHook(() => usePositions());
    
    await result.current.refreshPosition('pos_1');

    await waitFor(() => {
      expect(positionsApi.positionsApi.get).toHaveBeenCalledWith('pos_1');
    });
  });
});
