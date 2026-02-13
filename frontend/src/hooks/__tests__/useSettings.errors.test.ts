import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useSettings } from '../useSettings';

const mockSaveSettings = vi.fn();
const mockLoadSettings = vi.fn();

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
  saveSettings: mockSaveSettings,
  loadSettings: mockLoadSettings,
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

describe('useSettings - Error Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should handle save settings error', async () => {
    mockSaveSettings.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useSettings());

    await expect(result.current.saveSettings()).rejects.toThrow('Network error');
  });

  it('should handle load settings error', async () => {
    mockLoadSettings.mockRejectedValue(new Error('Failed to load'));

    const { result } = renderHook(() => useSettings());

    await result.current.loadSettings();

    await waitFor(() => {
      expect(mockLoadSettings).toHaveBeenCalled();
    });
  });

  it('should call loadSettings successfully', async () => {
    mockLoadSettings.mockResolvedValue(undefined);

    const { result } = renderHook(() => useSettings());

    await result.current.loadSettings();

    await waitFor(() => {
      expect(mockLoadSettings).toHaveBeenCalled();
    });
  });
});
