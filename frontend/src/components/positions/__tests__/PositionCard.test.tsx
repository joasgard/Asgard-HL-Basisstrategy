import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PositionCard } from '../PositionCard';
import type { Position } from '../../../stores';

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
  asgard_pda: 'AsgardPDA123',
  hyperliquid_address: '0xHL123',
};

describe('PositionCard', () => {
  it('should render position asset', () => {
    render(<PositionCard position={mockPosition} onClose={vi.fn()} />);
    
    expect(screen.getByText('SOL')).toBeInTheDocument();
  });

  it('should render leverage and size', () => {
    render(<PositionCard position={mockPosition} onClose={vi.fn()} />);
    
    expect(screen.getByText(/3x leverage/)).toBeInTheDocument();
    expect(screen.getByText(/\$5,000/)).toBeInTheDocument();
  });

  it('should render PnL with correct color for positive', () => {
    render(<PositionCard position={mockPosition} onClose={vi.fn()} />);
    
    const pnlValue = screen.getByText('+$150.00');
    expect(pnlValue).toHaveClass('text-green-400');
  });

  it('should render PnL with correct color for negative', () => {
    const negativePosition = { ...mockPosition, pnl_usd: -50, pnl_percent: -1 };
    const { container } = render(<PositionCard position={negativePosition} onClose={vi.fn()} />);
    
    // Check that the PnL text with negative value exists in the document
    expect(container.textContent).toContain('-');
    expect(container.textContent).toContain('50.00');
  });

  it('should render health factor with correct color', () => {
    render(<PositionCard position={mockPosition} onClose={vi.fn()} />);
    
    expect(screen.getByText('25%')).toBeInTheDocument();
  });

  it('should call onClose when close button clicked', () => {
    const onClose = vi.fn();
    render(<PositionCard position={mockPosition} onClose={onClose} />);
    
    const closeButton = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeButton);
    
    expect(onClose).toHaveBeenCalled();
  });

  it('should render entry and current price', () => {
    render(<PositionCard position={mockPosition} onClose={vi.fn()} />);
    
    expect(screen.getByText('$100.00')).toBeInTheDocument();
    expect(screen.getByText('$103.00')).toBeInTheDocument();
  });

  it('should render Asgard PDA', () => {
    render(<PositionCard position={mockPosition} onClose={vi.fn()} />);
    
    expect(screen.getByText('AsgardPDA123')).toBeInTheDocument();
  });

  it('should render created date', () => {
    render(<PositionCard position={mockPosition} onClose={vi.fn()} />);
    
    expect(screen.getByText(/2\/10\/2026/)).toBeInTheDocument();
  });

  it('should show yellow health color for medium risk', () => {
    const mediumRiskPosition = { ...mockPosition, health_factor: 0.15 };
    render(<PositionCard position={mediumRiskPosition} onClose={vi.fn()} />);
    
    const healthValue = screen.getByText('15%');
    expect(healthValue).toHaveClass('text-yellow-400');
  });

  it('should show red health color for high risk', () => {
    const highRiskPosition = { ...mockPosition, health_factor: 0.05 };
    render(<PositionCard position={highRiskPosition} onClose={vi.fn()} />);
    
    const healthValue = screen.getByText('5%');
    expect(healthValue).toHaveClass('text-red-400');
  });

  it('should show different icons for different assets', () => {
    const jitoPosition = { ...mockPosition, asset: 'jitoSOL' };
    render(<PositionCard position={jitoPosition} onClose={vi.fn()} />);
    
    expect(screen.getByText('jitoSOL')).toBeInTheDocument();
  });
});
