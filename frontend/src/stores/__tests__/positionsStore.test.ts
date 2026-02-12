import { describe, it, expect, beforeEach } from 'vitest';
import { usePositionsStore } from '../positionsStore';
import type { Position } from '../../api/positions';

const mockPosition: Position = {
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

describe('positionsStore', () => {
  beforeEach(() => {
    const store = usePositionsStore.getState();
    store.setPositions([]);
    store.setError(null);
    store.setLoading(false);
  });

  it('should have correct initial state', () => {
    const state = usePositionsStore.getState();
    expect(state.positions).toEqual([]);
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
    expect(state.totalPnl).toBe(0);
    expect(state.totalValue).toBe(0);
    expect(state.openPositionsCount).toBe(0);
  });

  it('should set positions and calculate stats', () => {
    const store = usePositionsStore.getState();
    const positions: Position[] = [
      mockPosition,
      { ...mockPosition, id: 'pos_2', pnl_usd: -50 },
    ];

    store.setPositions(positions);

    const state = usePositionsStore.getState();
    expect(state.positions).toHaveLength(2);
    expect(state.totalPnl).toBe(50); // 100 + (-50)
    expect(state.totalValue).toBe(10000); // 5000 * 2
    expect(state.openPositionsCount).toBe(2);
  });

  it('should add position and recalculate stats', () => {
    const store = usePositionsStore.getState();
    store.setPositions([mockPosition]);

    const newPosition: Position = { ...mockPosition, id: 'pos_2', pnl_usd: 200 };
    store.addPosition(newPosition);

    const state = usePositionsStore.getState();
    expect(state.positions).toHaveLength(2);
    expect(state.totalPnl).toBe(300); // 100 + 200
  });

  it('should update position', () => {
    const store = usePositionsStore.getState();
    store.setPositions([mockPosition]);

    store.updatePosition('pos_1', { pnl_usd: 150, current_price: 154 });

    const state = usePositionsStore.getState();
    expect(state.positions[0].pnl_usd).toBe(150);
    expect(state.positions[0].current_price).toBe(154);
    expect(state.totalPnl).toBe(150);
  });

  it('should remove position and recalculate stats', () => {
    const store = usePositionsStore.getState();
    store.setPositions([
      mockPosition,
      { ...mockPosition, id: 'pos_2', pnl_usd: 200 },
    ]);

    store.removePosition('pos_1');

    const state = usePositionsStore.getState();
    expect(state.positions).toHaveLength(1);
    expect(state.totalPnl).toBe(200);
  });

  it('should only count open positions in stats', () => {
    const store = usePositionsStore.getState();
    const positions: Position[] = [
      mockPosition,
      { ...mockPosition, id: 'pos_2', status: 'closed' },
    ];

    store.setPositions(positions);

    const state = usePositionsStore.getState();
    expect(state.openPositionsCount).toBe(1);
    expect(state.totalValue).toBe(5000); // Only open position
  });

  it('should select position', () => {
    const store = usePositionsStore.getState();
    store.selectPosition(mockPosition);

    const state = usePositionsStore.getState();
    expect(state.selectedPosition).toEqual(mockPosition);
  });
});
