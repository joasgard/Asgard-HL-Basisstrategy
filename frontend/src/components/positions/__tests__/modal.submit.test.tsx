import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { OpenPositionModal } from '../OpenPositionModal';
import { ClosePositionModal } from '../ClosePositionModal';
import type { Position } from '../../../stores';

const mockOpenPosition = vi.fn();
const mockClosePosition = vi.fn();
const mockSetGlobalLoading = vi.fn();

vi.mock('../../../hooks', () => ({
  usePositions: () => ({
    openPosition: mockOpenPosition,
    closePosition: mockClosePosition,
  }),
  useSettings: () => ({
    settings: {
      defaultLeverage: 3.0,
      minPositionSize: 100,
      maxPositionSize: 50000,
    },
  }),
}));

vi.mock('../../../stores', () => ({
  useUIStore: () => ({
    setGlobalLoading: mockSetGlobalLoading,
  }),
  useSettingsStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const store = {
      minPositionSize: 100,
      maxPositionSize: 50000,
      defaultLeverage: 3.0,
    };
    return selector ? selector(store) : store;
  },
}));

describe('Modal Form Submissions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('OpenPositionModal should set loading state on submit', async () => {
    mockOpenPosition.mockResolvedValue(undefined);
    
    render(<OpenPositionModal onClose={vi.fn()} />);
    
    // Get the form and submit it directly
    const form = document.querySelector('form');
    expect(form).toBeInTheDocument();
    
    if (form) {
      fireEvent.submit(form);
    }
    
    // Verify setGlobalLoading was called
    await waitFor(() => {
      expect(mockSetGlobalLoading).toHaveBeenCalledWith(true, 'Opening position...');
    });
  });

  it('ClosePositionModal should set loading state on submit', async () => {
    mockClosePosition.mockResolvedValue(undefined);
    
    const mockPosition: Position = {
      id: 'pos_1',
      asset: 'SOL',
      status: 'open',
      leverage: 3.0,
      size_usd: 5000,
      pnl_usd: 150,
      pnl_percent: 3,
      entry_price: 100,
      current_price: 103,
      health_factor: 0.25,
      created_at: '2026-02-10T00:00:00Z',
    };
    
    render(<ClosePositionModal position={mockPosition} onClose={vi.fn()} />);
    
    // Get the form and submit it directly
    const form = document.querySelector('form');
    if (form) {
      fireEvent.submit(form);
    } else {
      // Fallback: click the close button
      const closeButton = screen.getByRole('button', { name: /close position/i });
      fireEvent.click(closeButton);
    }
    
    await waitFor(() => {
      expect(mockSetGlobalLoading).toHaveBeenCalledWith(true, 'Closing position...');
    });
  });
});
