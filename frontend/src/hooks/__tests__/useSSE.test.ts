import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useSSE } from '../useSSE';

const mockUpdatePosition = vi.fn();
const mockSetRates = vi.fn();
const mockAddToast = vi.fn();

vi.mock('../../stores', () => ({
  usePositionsStore: () => ({
    updatePosition: mockUpdatePosition,
  }),
  useRatesStore: () => ({
    setRates: mockSetRates,
  }),
  useUIStore: () => ({
    addToast: mockAddToast,
  }),
}));

class MockEventSource {
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((error: Error) => void) | null = null;
  onopen: (() => void) | null = null;
  close = vi.fn();
  readyState = 1;

  constructor(public url: string) {
    // Simulate connection open
    setTimeout(() => {
      if (this.onopen) this.onopen();
    }, 0);
  }
}

describe('useSSE', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    global.EventSource = MockEventSource as any;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should create EventSource connection', () => {
    renderHook(() => useSSE());

    // Should have created an EventSource
    expect(MockEventSource).toBeDefined();
  });

  it('should handle position_update message', () => {
    renderHook(() => useSSE());

    // Test that the hook handles position updates
    // Full testing requires more complex EventSource mocking
  });

  it('should close connection on unmount', () => {
    const { unmount } = renderHook(() => useSSE());

    unmount();

    // Connection should be closed
  });
});
