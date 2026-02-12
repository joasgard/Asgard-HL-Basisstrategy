import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useSettings } from '../useSettings';

const mockStore = {
  defaultLeverage: 3.0,
  minPositionSize: 100,
  maxPositionSize: 50000,
  enableAutoExit: true,
  enableCircuitBreakers: true,
  maxFundingRate: 0.01,
  stopLossPercent: 10,
  takeProfitPercent: 50,
  selectedPreset: 'balanced',
  isLoading: false,
  error: null,
  isDirty: false,
  updateSettings: vi.fn(),
  applyPreset: vi.fn(),
  saveSettings: vi.fn(),
  loadSettings: vi.fn(),
  resetSettings: vi.fn(),
  setLoading: vi.fn(),
  setError: vi.fn(),
  markDirty: vi.fn(),
};

vi.mock('../../stores', () => ({
  useSettingsStore: (selector?: (state: unknown) => unknown) => {
    if (selector) {
      return selector(mockStore);
    }
    return mockStore;
  },
  useUIStore: () => ({
    addToast: vi.fn(),
  }),
  PRESETS: {
    conservative: { defaultLeverage: 2.0, minPositionSize: 500 },
    balanced: { defaultLeverage: 3.0, minPositionSize: 100 },
    aggressive: { defaultLeverage: 4.0, minPositionSize: 100 },
  },
}));

describe('useSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should return actions', () => {
    const { result } = renderHook(() => useSettings());

    expect(typeof result.current.updateSettings).toBe('function');
    expect(typeof result.current.applyPreset).toBe('function');
    expect(typeof result.current.saveSettings).toBe('function');
    expect(typeof result.current.loadSettings).toBe('function');
    expect(typeof result.current.resetSettings).toBe('function');
  });

  it('should update settings', () => {
    const { result } = renderHook(() => useSettings());

    result.current.updateSettings({ defaultLeverage: 2.5 });

    expect(mockStore.updateSettings).toHaveBeenCalledWith({ defaultLeverage: 2.5 });
  });

  it('should apply preset', () => {
    const { result } = renderHook(() => useSettings());

    result.current.applyPreset('aggressive');

    expect(mockStore.applyPreset).toHaveBeenCalledWith('aggressive');
  });

  it('should save settings', async () => {
    mockStore.saveSettings.mockResolvedValue(undefined);
    const { result } = renderHook(() => useSettings());

    await result.current.saveSettings();

    await waitFor(() => {
      expect(mockStore.saveSettings).toHaveBeenCalled();
    });
  });

  it('should load settings', async () => {
    mockStore.loadSettings.mockResolvedValue(undefined);
    const { result } = renderHook(() => useSettings());

    await result.current.loadSettings();

    await waitFor(() => {
      expect(mockStore.loadSettings).toHaveBeenCalled();
    });
  });

  it('should reset settings', () => {
    const { result } = renderHook(() => useSettings());

    result.current.resetSettings();

    expect(mockStore.resetSettings).toHaveBeenCalled();
  });
});
