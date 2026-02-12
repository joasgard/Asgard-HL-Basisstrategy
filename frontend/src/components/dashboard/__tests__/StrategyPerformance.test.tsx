import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StrategyPerformance } from '../StrategyPerformance';

vi.mock('../../../hooks', () => ({
  useRates: () => ({
    rates: {
      solana: { asset: 'SOL', rate: 15.3, annualizedRate: 15.3, source: 'kamino', timestamp: '' },
      hyperliquid: { asset: 'SOL', rate: -0.0025, annualizedRate: -3.0, source: 'hyperliquid', timestamp: '' },
      netRate: 18.5,
      netApy: 18.5,
      raw: {
        asgard: { kamino: 15.3, drift: 12.1 },
        asgard_details: { lending_apy: 25.5, borrowing_apy: 10.2, net_apy: 15.3 },
        hyperliquid: { funding_rate: -0.0025, predicted: -0.003, annualized: -3.0 },
        combined: { kamino: 18.5, drift: 15.2 },
        leverage: 3.0,
      },
    },
    isLoading: false,
    error: null,
    lastUpdated: new Date(),
    fetchRates: vi.fn(),
  }),
}));

describe('StrategyPerformance', () => {
  it('should render section title', () => {
    render(<StrategyPerformance leverage={3.0} />);

    expect(screen.getByText('Strategy Performance')).toBeInTheDocument();
  });

  it('should display leverage multiplier', () => {
    render(<StrategyPerformance leverage={3.0} />);

    expect(screen.getByText('Net APY @ 3.0x')).toBeInTheDocument();
  });

  it('should render Combined Net APY label', () => {
    render(<StrategyPerformance leverage={3.0} />);

    expect(screen.getByText('Combined Net APY')).toBeInTheDocument();
  });

  it('should display net APY from API', () => {
    render(<StrategyPerformance leverage={3.0} />);

    expect(screen.getByText('18.50%')).toBeInTheDocument();
  });

  it('should render funding annualized info', () => {
    render(<StrategyPerformance leverage={3.0} />);

    expect(screen.getByText('HL Funding (annualized)')).toBeInTheDocument();
    expect(screen.getByText('-3.00%')).toBeInTheDocument();
  });

  it('should render Asgard net APY', () => {
    render(<StrategyPerformance leverage={3.0} />);

    expect(screen.getByText('Asgard Net APY')).toBeInTheDocument();
    expect(screen.getByText('15.30%')).toBeInTheDocument();
  });

  it('should display best protocol name', () => {
    render(<StrategyPerformance leverage={3.0} />);

    expect(screen.getByText('via kamino')).toBeInTheDocument();
  });
});
