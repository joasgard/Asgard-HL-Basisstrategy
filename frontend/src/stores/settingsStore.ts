import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface StrategySettings {
  defaultLeverage: number;
  minPositionSize: number;
  maxPositionSize: number;
  maxPositionsPerAsset: number;
  minOpportunityApy: number;
  maxFundingVolatility: number;
  priceDeviationThreshold: number;
  deltaDriftThreshold: number;
  stopLossPercent: number;
  takeProfitPercent: number;
  enableAutoExit: boolean;
  enableCircuitBreakers: boolean;
}

export type PresetType = 'conservative' | 'balanced' | 'aggressive';

export const PRESETS: Record<PresetType, Partial<StrategySettings>> = {
  conservative: {
    defaultLeverage: 2.0,
    minPositionSize: 500,
    maxPositionsPerAsset: 1,
    minOpportunityApy: 2.0,
    maxFundingVolatility: 30,
    priceDeviationThreshold: 0.3,
    deltaDriftThreshold: 0.3,
    stopLossPercent: 5,
    takeProfitPercent: 30,
    enableAutoExit: true,
    enableCircuitBreakers: true,
  },
  balanced: {
    defaultLeverage: 3.0,
    minPositionSize: 100,
    maxPositionsPerAsset: 2,
    minOpportunityApy: 1.0,
    maxFundingVolatility: 50,
    priceDeviationThreshold: 0.5,
    deltaDriftThreshold: 0.5,
    stopLossPercent: 10,
    takeProfitPercent: 50,
    enableAutoExit: true,
    enableCircuitBreakers: true,
  },
  aggressive: {
    defaultLeverage: 4.0,
    minPositionSize: 100,
    maxPositionsPerAsset: 3,
    minOpportunityApy: 0.5,
    maxFundingVolatility: 80,
    priceDeviationThreshold: 1.0,
    deltaDriftThreshold: 1.0,
    stopLossPercent: 15,
    takeProfitPercent: 100,
    enableAutoExit: false,
    enableCircuitBreakers: false,
  },
};

interface SettingsState extends StrategySettings {
  selectedPreset: PresetType;
  isLoading: boolean;
  error: string | null;
  isDirty: boolean;
  
  // Actions
  updateSettings: (settings: Partial<StrategySettings>) => void;
  applyPreset: (preset: PresetType) => void;
  saveSettings: () => Promise<void>;
  loadSettings: () => Promise<void>;
  resetSettings: () => void;
  setLoading: (value: boolean) => void;
  setError: (error: string | null) => void;
  markDirty: (value: boolean) => void;
}

const DEFAULT_SETTINGS: StrategySettings = {
  defaultLeverage: 3.0,
  minPositionSize: 100,
  maxPositionSize: 50000,
  maxPositionsPerAsset: 2,
  minOpportunityApy: 1.0,
  maxFundingVolatility: 50,
  priceDeviationThreshold: 0.5,
  deltaDriftThreshold: 0.5,
  stopLossPercent: 10,
  takeProfitPercent: 50,
  enableAutoExit: true,
  enableCircuitBreakers: true,
};

// Helper to convert camelCase to snake_case for API
const toSnakeCase = (obj: Record<string, unknown>): Record<string, unknown> => {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    const snakeKey = key.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`);
    result[snakeKey] = value;
  }
  return result;
};

// Helper to convert snake_case to camelCase from API
const toCamelCase = (obj: Record<string, unknown>): Record<string, unknown> => {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
    result[camelKey] = value;
  }
  return result;
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      ...DEFAULT_SETTINGS,
      selectedPreset: 'balanced',
      isLoading: false,
      error: null,
      isDirty: false,

      updateSettings: (settings) => {
        set({ ...settings, isDirty: true });
      },

      applyPreset: (preset) => {
        const presetSettings = PRESETS[preset];
        set({ ...presetSettings, selectedPreset: preset, isDirty: true });
      },

      saveSettings: async () => {
        set({ isLoading: true, error: null });
        try {
          const settings = get();
          const settingsToSave = {
            defaultLeverage: settings.defaultLeverage,
            minPositionSize: settings.minPositionSize,
            maxPositionSize: settings.maxPositionSize,
            maxPositionsPerAsset: settings.maxPositionsPerAsset,
            minOpportunityApy: settings.minOpportunityApy,
            maxFundingVolatility: settings.maxFundingVolatility,
            priceDeviationThreshold: settings.priceDeviationThreshold,
            deltaDriftThreshold: settings.deltaDriftThreshold,
            stopLossPercent: settings.stopLossPercent,
            takeProfitPercent: settings.takeProfitPercent,
            enableAutoExit: settings.enableAutoExit,
            enableCircuitBreakers: settings.enableCircuitBreakers,
          };
          
          const response = await fetch('/api/v1/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(toSnakeCase(settingsToSave)),
          });
          
          if (!response.ok) throw new Error('Failed to save settings');
          set({ isDirty: false });
        } catch (error) {
          set({ error: error instanceof Error ? error.message : 'Unknown error' });
        } finally {
          set({ isLoading: false });
        }
      },

      loadSettings: async () => {
        set({ isLoading: true, error: null });
        try {
          const response = await fetch('/api/v1/settings');
          if (!response.ok) throw new Error('Failed to load settings');
          const data = await response.json();
          if (data.settings) {
            const camelSettings = toCamelCase(data.settings as Record<string, unknown>);
            set({ ...camelSettings, isDirty: false });
          }
        } catch (error) {
          set({ error: error instanceof Error ? error.message : 'Unknown error' });
        } finally {
          set({ isLoading: false });
        }
      },

      resetSettings: () => {
        set({ ...DEFAULT_SETTINGS, selectedPreset: 'balanced', isDirty: true });
      },

      setLoading: (value) => set({ isLoading: value }),
      setError: (error) => set({ error }),
      markDirty: (value) => set({ isDirty: value }),
    }),
    {
      name: 'settings-storage',
      partialize: (state) => ({
        defaultLeverage: state.defaultLeverage,
        minPositionSize: state.minPositionSize,
        maxPositionSize: state.maxPositionSize,
        maxPositionsPerAsset: state.maxPositionsPerAsset,
        minOpportunityApy: state.minOpportunityApy,
        maxFundingVolatility: state.maxFundingVolatility,
        priceDeviationThreshold: state.priceDeviationThreshold,
        deltaDriftThreshold: state.deltaDriftThreshold,
        stopLossPercent: state.stopLossPercent,
        takeProfitPercent: state.takeProfitPercent,
        enableAutoExit: state.enableAutoExit,
        enableCircuitBreakers: state.enableCircuitBreakers,
        selectedPreset: state.selectedPreset,
      }),
    }
  )
);
