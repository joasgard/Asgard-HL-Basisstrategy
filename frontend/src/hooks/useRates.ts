import { useCallback, useEffect, useRef } from 'react';
import { useRatesStore, useUIStore } from '../stores';
import { ratesApi, type RatesResponse } from '../api/rates';

// Stable selector hooks to avoid re-render loops
const useSetRates = () => useRatesStore((s) => s.setRates);
const useSetLoading = () => useRatesStore((s) => s.setLoading);
const useSetError = () => useRatesStore((s) => s.setError);

export function useRates(leverage: number = 3.0) {
  const setRates = useSetRates();
  const setLoading = useSetLoading();
  const setError = useSetError();
  const { addToast } = useUIStore();
  const leverageRef = useRef(leverage);
  leverageRef.current = leverage;

  const fetchRates = useCallback(async (lev?: number) => {
    const effectiveLeverage = lev ?? leverageRef.current;
    setLoading(true);
    setError(null);

    try {
      const data: RatesResponse = await ratesApi.getCurrent(effectiveLeverage);

      // Find best combined protocol
      const combinedEntries = Object.entries(data.combined);
      const best = combinedEntries.length > 0
        ? combinedEntries.reduce((a, b) => (a[1] > b[1] ? a : b))
        : null;

      setRates({
        solana: {
          asset: 'SOL',
          rate: data.asgard_details?.net_apy ?? 0,
          annualizedRate: data.asgard_details?.net_apy ?? 0,
          source: best ? best[0] : 'unknown',
          timestamp: new Date().toISOString(),
        },
        hyperliquid: {
          asset: 'SOL',
          rate: data.hyperliquid.funding_rate,
          annualizedRate: data.hyperliquid.annualized,
          source: 'hyperliquid',
          timestamp: new Date().toISOString(),
        },
        netRate: best ? best[1] : 0,
        netApy: best ? best[1] : 0,
        raw: data,
      });
    } catch (error) {
      if (error instanceof Error && error.message?.includes('401')) {
        // Silent fail for auth errors
      } else {
        const message = error instanceof Error ? error.message : 'Failed to fetch rates';
        setError(message);
        addToast(message, 'error');
      }
    } finally {
      setLoading(false);
    }
  }, [setRates, setLoading, setError, addToast]);

  // Auto-refresh rates every 60 seconds
  useEffect(() => {
    fetchRates(leverage);

    const interval = setInterval(() => {
      fetchRates(leverage);
    }, 60000);

    return () => clearInterval(interval);
  }, [fetchRates, leverage]);

  return {
    rates: useRatesStore((s) => s.rates),
    isLoading: useRatesStore((s) => s.isLoading),
    error: useRatesStore((s) => s.error),
    lastUpdated: useRatesStore((s) => s.lastUpdated),
    fetchRates,
  };
}
