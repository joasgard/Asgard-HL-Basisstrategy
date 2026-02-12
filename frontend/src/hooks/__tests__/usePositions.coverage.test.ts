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
  usePositionsStore: () => mockStore,
  useUIStore: () => ({
    addToast: vi.fn(),
  }),
}));

describe('usePositions - Additional Coverage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should handle list error with non-Error object', async () => {
    (positionsApi.positionsApi.list as ReturnType<typeof vi.fn>).mockRejectedValue('String error');

    const { result } = renderHook(() => usePositions());
    await result.current.fetchPositions();

    await waitFor(() => {
      expect(mockStore.setError).toHaveBeenCalledWith('Failed to fetch positions');
    });
  });

  it('should handle open position non-Error error', async () => {
    (positionsApi.positionsApi.open as ReturnType<typeof vi.fn>).mockRejectedValue('Error string');

    const { result } = renderHook(() => usePositions());
    
    await expect(result.current.openPosition('SOL', 3.0, 5000)).rejects.toThrow();
  });

  it('should handle close position non-Error error', async () => {
    (positionsApi.positionsApi.close as ReturnType<typeof vi.fn>).mockRejectedValue('Error string');

    const { result } = renderHook(() => usePositions());
    
    await expect(result.current.closePosition('pos_1')).rejects.toThrow();
  });

  it('should handle refresh position non-Error error', async () => {
    (positionsApi.positionsApi.get as ReturnType<typeof vi.fn>).mockRejectedValue('Error string');

    const { result } = renderHook(() => usePositions());
    
    await expect(result.current.refreshPosition('pos_1')).rejects.toThrow();
  });

  it('should call selectPosition', () => {
    const { result } = renderHook(() => usePositions());
    
    const position = { id: 'pos_1', asset: 'SOL' };
    result.current.selectPosition(position as any);

    expect(mockStore.selectPosition).toHaveBeenCalledWith(position);
  });

  it('should handle successful list response', async () => {
    const mockPositions = [
      { id: 'pos_1', asset: 'SOL', status: 'open' },
      { id: 'pos_2', asset: 'ETH', status: 'closed' },
    ];
    (positionsApi.positionsApi.list as ReturnType<typeof vi.fn>).mockResolvedValue(mockPositions);

    const { result } = renderHook(() => usePositions());
    await result.current.fetchPositions();

    await waitFor(() => {
      expect(mockStore.setPositions).toHaveBeenCalledWith(mockPositions);
      expect(mockStore.setLoading).toHaveBeenLastCalledWith(false);
    });
  });

  it('should handle successful refresh', async () => {
    const mockPosition = { id: 'pos_1', asset: 'SOL', status: 'open' };
    (positionsApi.positionsApi.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockPosition);

    const { result } = renderHook(() => usePositions());
    await result.current.refreshPosition('pos_1');

    await waitFor(() => {
      expect(mockStore.updatePosition).toHaveBeenCalledWith('pos_1', mockPosition);
    });
  });
});
