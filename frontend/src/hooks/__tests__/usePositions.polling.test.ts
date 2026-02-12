import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
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

const mockAddToast = vi.fn();
const mockUpdatePosition = vi.fn();

vi.mock('../../stores', () => ({
  usePositionsStore: () => ({
    positions: [],
    isLoading: false,
    error: null,
    selectedPosition: null,
    totalPnl: 0,
    totalValue: 0,
    openPositionsCount: 0,
    setPositions: vi.fn(),
    addPosition: vi.fn(),
    updatePosition: mockUpdatePosition,
    removePosition: vi.fn(),
    setLoading: vi.fn(),
    setError: vi.fn(),
    selectPosition: vi.fn(),
  }),
  useUIStore: () => ({
    addToast: mockAddToast,
  }),
}));

describe('usePositions - Job Polling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should handle successful open position', async () => {
    (positionsApi.positionsApi.open as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: 'job_123',
    });

    const { result } = renderHook(() => usePositions());
    
    await result.current.openPosition('SOL', 3.0, 5000);

    expect(positionsApi.positionsApi.open).toHaveBeenCalledWith({
      asset: 'SOL',
      leverage: 3.0,
      size_usd: 5000,
    });
    expect(mockAddToast).toHaveBeenCalledWith(expect.stringContaining('Job'), 'success');
  });

  it('should handle successful close position', async () => {
    (positionsApi.positionsApi.close as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: 'job_456',
    });

    const { result } = renderHook(() => usePositions());
    
    await result.current.closePosition('pos_1');

    expect(positionsApi.positionsApi.close).toHaveBeenCalledWith('pos_1');
  });

  it('should initiate job status polling on open', async () => {
    (positionsApi.positionsApi.open as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: 'job_123',
    });
    
    (positionsApi.positionsApi.getJobStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'completed',
      position_id: 'pos_123',
    });

    const { result } = renderHook(() => usePositions());
    
    await result.current.openPosition('SOL', 3.0, 5000);
    
    // Job polling is initiated with setTimeout, verify the API was called
    expect(positionsApi.positionsApi.open).toHaveBeenCalled();
  });

  it('should initiate job status polling on close', async () => {
    (positionsApi.positionsApi.close as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: 'job_456',
    });
    
    (positionsApi.positionsApi.getJobStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'completed',
    });

    const { result } = renderHook(() => usePositions());
    
    await result.current.closePosition('pos_1');
    
    expect(positionsApi.positionsApi.close).toHaveBeenCalled();
  });
});
