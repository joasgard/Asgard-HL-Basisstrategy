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

describe('ClosePositionModal', () => {
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

  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render modal with title', () => {
    const { container } = render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    expect(container.textContent).toContain('Close Position');
  });

  it('should render warning message', () => {
    render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    expect(screen.getByText(/confirm position closure/i)).toBeInTheDocument();
  });

  it('should display position details', () => {
    render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    expect(screen.getByText('SOL')).toBeInTheDocument();
    expect(screen.getByText('$5,000')).toBeInTheDocument();
    expect(screen.getByText('3x')).toBeInTheDocument();
  });

  it('should display PnL', () => {
    render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    expect(screen.getByText('+\$150.00')).toBeInTheDocument();
  });

  it('should call onClose when cancel clicked', () => {
    render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancelButton);
    
    expect(onClose).toHaveBeenCalled();
  });

  it('should call closePosition when confirm clicked', async () => {
    mockClosePosition.mockResolvedValue(undefined);
    
    render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    const closeButton = screen.getByRole('button', { name: /close position/i });
    fireEvent.click(closeButton);
    
    await waitFor(() => {
      expect(mockClosePosition).toHaveBeenCalledWith('pos_1');
    });
  });

  it('should show loading state when closing', async () => {
    mockClosePosition.mockImplementation(() => new Promise(() => {}));
    
    render(<ClosePositionModal position={mockPosition} onClose={onClose} />);
    
    const closeButton = screen.getByRole('button', { name: /close position/i });
    fireEvent.click(closeButton);
    
    await waitFor(() => {
      expect(mockSetGlobalLoading).toHaveBeenCalledWith(true, 'Closing position...');
    });
  });

  it('should handle negative PnL display', () => {
    const negativePosition = { ...mockPosition, pnl_usd: -50 };
    const { container } = render(<ClosePositionModal position={negativePosition} onClose={onClose} />);
    
    // Check for negative sign and amount
    expect(container.textContent).toContain('-');
    expect(container.textContent).toContain('50.00');
  });
});
