import { describe, it, expect, beforeEach } from 'vitest';
import { usePositionsStore } from '../positionsStore';

describe('positionsStore - Branch Coverage', () => {
  beforeEach(() => {
    const store = usePositionsStore.getState();
    store.setPositions([]);
  });

  it('should handle calculateStats with no positions', () => {
    const store = usePositionsStore.getState();
    
    store.setPositions([]);
    
    const state = usePositionsStore.getState();
    expect(state.totalPnl).toBe(0);
    expect(state.totalValue).toBe(0);
    expect(state.openPositionsCount).toBe(0);
  });

  it('should handle calculateStats with mixed status positions', () => {
    const store = usePositionsStore.getState();
    
    store.setPositions([
      { id: '1', status: 'open', size_usd: 1000, pnl_usd: 50 } as any,
      { id: '2', status: 'closed', size_usd: 2000, pnl_usd: 100 } as any,
      { id: '3', status: 'closing', size_usd: 1500, pnl_usd: -25 } as any,
    ]);
    
    const state = usePositionsStore.getState();
    expect(state.totalPnl).toBe(125); // 50 + 100 + (-25)
    expect(state.totalValue).toBe(1000); // Only open position
    expect(state.openPositionsCount).toBe(1);
  });

  it('should handle addPosition with recalculation', () => {
    const store = usePositionsStore.getState();
    store.setPositions([{ id: '1', status: 'open', size_usd: 1000, pnl_usd: 50 } as any]);
    
    store.addPosition({ id: '2', status: 'open', size_usd: 2000, pnl_usd: 100 } as any);
    
    const state = usePositionsStore.getState();
    expect(state.positions).toHaveLength(2);
    expect(state.totalPnl).toBe(150);
    expect(state.totalValue).toBe(3000);
  });

  it('should handle removePosition with recalculation', () => {
    const store = usePositionsStore.getState();
    store.setPositions([
      { id: '1', status: 'open', size_usd: 1000, pnl_usd: 50 } as any,
      { id: '2', status: 'open', size_usd: 2000, pnl_usd: 100 } as any,
    ]);
    
    store.removePosition('1');
    
    const state = usePositionsStore.getState();
    expect(state.positions).toHaveLength(1);
    expect(state.totalPnl).toBe(100);
    expect(state.totalValue).toBe(2000);
  });

  it('should handle updatePosition with recalculation', () => {
    const store = usePositionsStore.getState();
    store.setPositions([
      { id: '1', status: 'open', size_usd: 1000, pnl_usd: 50 } as any,
      { id: '2', status: 'open', size_usd: 2000, pnl_usd: 100 } as any,
    ]);
    
    store.updatePosition('1', { pnl_usd: 75 });
    
    const state = usePositionsStore.getState();
    expect(state.totalPnl).toBe(175); // 75 + 100
  });
});
