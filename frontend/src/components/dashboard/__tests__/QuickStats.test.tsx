import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QuickStats } from '../QuickStats';

vi.mock('@privy-io/react-auth', () => ({
  usePrivy: () => ({
    authenticated: false,
    login: vi.fn(),
  }),
}));

vi.mock('../../../hooks', () => ({
  usePositions: () => ({
    fetchPositions: vi.fn(),
  }),
  useBalances: () => ({
    balances: null,
    isLoading: false,
    solBalance: 0,
    solUsdc: 0,
    ethBalance: 0,
    arbUsdc: 0,
    hlBalance: 0,
    refetch: vi.fn(),
  }),
}));

vi.mock('../../../stores', () => ({
  usePositionsStore: (selector: (s: Record<string, unknown>) => unknown) => selector({
    totalPnl: 0,
    totalValue: 0,
    openPositionsCount: 0,
  }),
}));

describe('QuickStats', () => {
  it('should render section title', () => {
    render(<QuickStats />);

    expect(screen.getByText('Quick Stats')).toBeInTheDocument();
  });

  it('should render open positions label', () => {
    render(<QuickStats />);

    expect(screen.getByText('Open Positions')).toBeInTheDocument();
  });

  it('should render Total PnL label', () => {
    render(<QuickStats />);

    expect(screen.getByText('Total PnL')).toBeInTheDocument();
  });

  it('should render total value label', () => {
    render(<QuickStats />);

    expect(screen.getByText('Total Value')).toBeInTheDocument();
  });

  it('should show dashes when not authenticated', () => {
    render(<QuickStats />);

    // All three values should show "—" when not logged in
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBe(3);
  });
});
