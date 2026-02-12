import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ClosePositionModal } from '../ClosePositionModal';
import type { Position } from '../../../stores';

const mockClosePosition = vi.fn();
const mockSetGlobalLoading = vi.fn();

vi.mock('../../../hooks', () => ({
  usePositions: () => ({
    closePosition: mockClosePosition,
  }),
}));

vi.mock('../../../stores', () => ({
  useUIStore: () => ({
    setGlobalLoading: mockSetGlobalLoading,
  }),
}));

describe('ClosePositionModal - Coverage', () => {
  const mockPosition: Position = {
    id: 'pos_1',
    asset: 'SOL',
    status: 'open',
    leverage: 3.0,
    size_usd: 5000,
    pnl_usd: -50,
    pnl_percent: -1,
    entry_price: 100,
    current_price: 97,
    health_factor: 0.25,
    created_at: '2026-02-10T00:00:00Z',
  };

  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render with negative PnL styling', () => {
    const { container } = render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    // Should show negative PnL
    expect(container.textContent).toContain('-');
    expect(container.textContent).toContain('50.00');
  });

  it('should render warning icon SVG', () => {
    const { container } = render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    // SVG should be present
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });

  it('should render all position details', () => {
    render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    expect(screen.getByText('Asset')).toBeInTheDocument();
    expect(screen.getByText('Size')).toBeInTheDocument();
    expect(screen.getByText('Leverage')).toBeInTheDocument();
    expect(screen.getByText('Entry Price')).toBeInTheDocument();
    expect(screen.getByText('PnL')).toBeInTheDocument();
  });

  it('should call setGlobalLoading when closing', async () => {
    mockClosePosition.mockResolvedValue(undefined);
    
    render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    const closeButton = screen.getByRole('button', { name: /close position/i });
    fireEvent.click(closeButton);
    
    await waitFor(() => {
      expect(mockSetGlobalLoading).toHaveBeenCalledWith(true, 'Closing position...');
    });
  });

  it('should render close button icon', () => {
    const { container } = render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    // Close icon SVG
    const closeIcon = container.querySelector('svg[class*="w-6"]');
    expect(closeIcon).toBeInTheDocument();
  });
});
