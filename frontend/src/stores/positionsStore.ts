import { create } from 'zustand';
import type { Position } from '../api/positions';

export type { Position };

interface PositionsState {
  positions: Position[];
  isLoading: boolean;
  error: string | null;
  selectedPosition: Position | null;
  
  // Stats
  totalPnl: number;
  totalValue: number;
  openPositionsCount: number;
  
  // Actions
  setPositions: (positions: Position[]) => void;
  addPosition: (position: Position) => void;
  updatePosition: (id: string, updates: Partial<Position>) => void;
  removePosition: (id: string) => void;
  setLoading: (value: boolean) => void;
  setError: (error: string | null) => void;
  selectPosition: (position: Position | null) => void;
  calculateStats: () => void;
}

export const usePositionsStore = create<PositionsState>((set, get) => ({
  positions: [],
  isLoading: false,
  error: null,
  selectedPosition: null,
  totalPnl: 0,
  totalValue: 0,
  openPositionsCount: 0,

  setPositions: (positions) => {
    set({ positions: Array.isArray(positions) ? positions : [] });
    get().calculateStats();
  },

  addPosition: (position) => {
    set((state) => ({ positions: [position, ...state.positions] }));
    get().calculateStats();
  },

  updatePosition: (id, updates) => {
    set((state) => ({
      positions: state.positions.map((p) =>
        p.id === id ? { ...p, ...updates } : p
      ),
    }));
    get().calculateStats();
  },

  removePosition: (id) => {
    set((state) => ({
      positions: state.positions.filter((p) => p.id !== id),
    }));
    get().calculateStats();
  },

  setLoading: (value) => set({ isLoading: value }),
  setError: (error) => set({ error }),
  selectPosition: (position) => set({ selectedPosition: position }),

  calculateStats: () => {
    const { positions } = get();
    const openPositions = positions.filter((p) => p.status === 'open');
    
    set({
      totalPnl: positions.reduce((sum, p) => sum + p.pnl_usd, 0),
      totalValue: openPositions.reduce((sum, p) => sum + p.size_usd, 0),
      openPositionsCount: openPositions.length,
    });
  },
}));
