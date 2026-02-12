import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useSettingsStore, PRESETS } from '../settingsStore';

describe('settingsStore', () => {
  beforeEach(() => {
    const store = useSettingsStore.getState();
    store.resetSettings();
    store.setError(null);
    store.setLoading(false);
  });

  it('should have correct initial state', () => {
    const state = useSettingsStore.getState();
    expect(state.defaultLeverage).toBe(3.0);
    expect(state.minPositionSize).toBe(100);
    expect(state.maxPositionSize).toBe(50000);
    expect(state.enableAutoExit).toBe(true);
    expect(state.enableCircuitBreakers).toBe(true);
    expect(state.selectedPreset).toBe('balanced');
  });

  it('should update settings and mark dirty', () => {
    const store = useSettingsStore.getState();
    store.updateSettings({ defaultLeverage: 2.5 });

    const state = useSettingsStore.getState();
    expect(state.defaultLeverage).toBe(2.5);
    expect(state.isDirty).toBe(true);
  });

  it('should apply conservative preset', () => {
    const store = useSettingsStore.getState();
    store.applyPreset('conservative');

    const state = useSettingsStore.getState();
    expect(state.defaultLeverage).toBe(PRESETS.conservative.defaultLeverage);
    expect(state.minPositionSize).toBe(PRESETS.conservative.minPositionSize);
    expect(state.selectedPreset).toBe('conservative');
    expect(state.isDirty).toBe(true);
  });

  it('should apply aggressive preset', () => {
    const store = useSettingsStore.getState();
    store.applyPreset('aggressive');

    const state = useSettingsStore.getState();
    expect(state.defaultLeverage).toBe(PRESETS.aggressive.defaultLeverage);
    expect(state.enableAutoExit).toBe(PRESETS.aggressive.enableAutoExit);
    expect(state.enableCircuitBreakers).toBe(PRESETS.aggressive.enableCircuitBreakers);
    expect(state.selectedPreset).toBe('aggressive');
  });

  it('should reset to defaults', () => {
    const store = useSettingsStore.getState();
    store.updateSettings({ defaultLeverage: 4.5 });
    store.applyPreset('aggressive');

    store.resetSettings();

    const state = useSettingsStore.getState();
    expect(state.defaultLeverage).toBe(3.0);
    expect(state.selectedPreset).toBe('balanced');
    expect(state.isDirty).toBe(true);
  });

  it('should save settings to API', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    const store = useSettingsStore.getState();
    store.updateSettings({ defaultLeverage: 2.5 });

    await store.saveSettings();

    const state = useSettingsStore.getState();
    expect(state.isDirty).toBe(false);
    expect(state.isLoading).toBe(false);
    expect(fetch).toHaveBeenCalledWith('/api/v1/settings', expect.any(Object));
  });

  it('should handle save settings error', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
    });

    const store = useSettingsStore.getState();
    await store.saveSettings();

    const state = useSettingsStore.getState();
    expect(state.error).not.toBeNull();
    expect(state.isLoading).toBe(false);
  });

  it('should load settings from API', async () => {
    const mockSettings = {
      defaultLeverage: 2.0,
      minPositionSize: 500,
      maxPositionSize: 10000,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockSettings),
    });

    const store = useSettingsStore.getState();
    await store.loadSettings();

    const state = useSettingsStore.getState();
    expect(state.defaultLeverage).toBe(2.0);
    expect(state.minPositionSize).toBe(500);
    expect(state.isDirty).toBe(false);
  });
});
