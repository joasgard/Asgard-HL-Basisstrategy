import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useSettingsStore } from '../settingsStore';

describe('settingsStore - Branch Coverage', () => {
  beforeEach(() => {
    const store = useSettingsStore.getState();
    store.resetSettings();
    store.setError(null);
  });

  it('should handle saveSettings with network error', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network failed'));

    const store = useSettingsStore.getState();
    await store.saveSettings();

    const state = useSettingsStore.getState();
    expect(state.error).toBe('Network failed');
    expect(state.isLoading).toBe(false);
  });

  it('should handle loadSettings with network error', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Fetch failed'));

    const store = useSettingsStore.getState();
    await store.loadSettings();

    const state = useSettingsStore.getState();
    expect(state.error).toBe('Fetch failed');
    expect(state.isLoading).toBe(false);
  });

  it('should handle loadSettings with invalid response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });

    const store = useSettingsStore.getState();
    await store.loadSettings();

    const state = useSettingsStore.getState();
    expect(state.error).not.toBeNull();
  });

  it('should handle saveSettings with all settings', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    const store = useSettingsStore.getState();
    // Set all required settings
    store.updateSettings({
      defaultLeverage: 2.5,
      minPositionSize: 200,
      maxPositionSize: 25000,
      enableAutoExit: false,
      enableCircuitBreakers: false,
      maxPositionsPerAsset: 2,
      minOpportunityApy: 1.5,
      maxFundingVolatility: 40,
      priceDeviationThreshold: 0.4,
      deltaDriftThreshold: 0.4,
      stopLossPercent: 15,
      takeProfitPercent: 60,
    });

    await store.saveSettings();

    const state = useSettingsStore.getState();
    expect(state.isDirty).toBe(false);
  });

  it('should handle multiple preset applications', () => {
    const store = useSettingsStore.getState();
    
    store.applyPreset('conservative');
    expect(useSettingsStore.getState().selectedPreset).toBe('conservative');
    
    store.applyPreset('aggressive');
    expect(useSettingsStore.getState().selectedPreset).toBe('aggressive');
    
    store.applyPreset('balanced');
    expect(useSettingsStore.getState().selectedPreset).toBe('balanced');
  });

  it('should mark dirty on multiple updates', () => {
    const store = useSettingsStore.getState();
    
    store.updateSettings({ defaultLeverage: 2.0 });
    expect(useSettingsStore.getState().isDirty).toBe(true);
    
    // Save to reset dirty
    store.markDirty(false);
    expect(useSettingsStore.getState().isDirty).toBe(false);
    
    store.updateSettings({ minPositionSize: 500 });
    expect(useSettingsStore.getState().isDirty).toBe(true);
  });
});
