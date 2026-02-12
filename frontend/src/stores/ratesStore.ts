import { create } from 'zustand';
import type { RatesResponse } from '../api/rates';

export interface FundingRate {
  asset: string;
  rate: number; // APY % for Asgard, hourly % for Hyperliquid
  annualizedRate: number;
  source: string;
  timestamp: string;
}

export interface RatesData {
  solana: FundingRate;
  hyperliquid: FundingRate;
  netRate: number;   // Best combined APY %
  netApy: number;    // Best combined APY %
  raw?: RatesResponse; // Raw backend response
}

interface RatesState {
  rates: RatesData | null;
  historicalRates: FundingRate[];
  isLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;

  // Actions
  setRates: (rates: RatesData) => void;
  setHistoricalRates: (rates: FundingRate[]) => void;
  setLoading: (value: boolean) => void;
  setError: (error: string | null) => void;

  // Computed
  getNetApyAtLeverage: (leverage: number) => number;
}

export const useRatesStore = create<RatesState>((set, get) => ({
  rates: null,
  historicalRates: [],
  isLoading: false,
  error: null,
  lastUpdated: null,

  setRates: (rates) => set({ rates, lastUpdated: new Date() }),
  setHistoricalRates: (rates) => set({ historicalRates: rates }),
  setLoading: (value) => set({ isLoading: value }),
  setError: (error) => set({ error }),

  getNetApyAtLeverage: (_leverage: number) => {
    const { rates } = get();
    if (!rates) return 0;
    // Rates are already at the requested leverage (backend calculates per-request)
    return rates.netApy;
  },
}));
