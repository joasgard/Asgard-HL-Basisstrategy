import { useState, useEffect, useCallback, useRef } from 'react';
import { usePrivy } from '@privy-io/react-auth';
import { apiClient } from '../api/client';

interface TokenBalance {
  symbol: string;
  balance: number;
  usd_value: number | null;
}

interface ChainBalance {
  address: string;
  native_balance: number;
  native_symbol: string;
  tokens: TokenBalance[];
}

export interface Balances {
  solana: ChainBalance | null;
  arbitrum: ChainBalance | null;
  hyperliquid_clearinghouse: number | null;
  total_usd_value: number | null;
  has_sufficient_funds: boolean;
}

const POLL_INTERVAL_MS = 30_000; // 30 seconds

export function useBalances() {
  const { authenticated } = usePrivy();
  const [balances, setBalances] = useState<Balances | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchBalances = useCallback(async () => {
    if (!authenticated) {
      setBalances(null);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const { data } = await apiClient.get('/balances');
      setBalances(data);
    } catch (e: any) {
      // 401 is expected before backend session is established — not an error
      if (e.httpStatus === 401) {
        setBalances(null);
      } else {
        setError(e.message || 'Failed to fetch balances');
      }
    } finally {
      setIsLoading(false);
    }
  }, [authenticated]);

  // Initial fetch + polling
  useEffect(() => {
    fetchBalances();

    // Poll to recover from initial 401 and keep balances fresh
    if (authenticated) {
      intervalRef.current = setInterval(fetchBalances, POLL_INTERVAL_MS);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [fetchBalances, authenticated]);

  // Helper to get USDC balance for a chain
  const getUsdc = (chain: ChainBalance | null): number => {
    if (!chain) return 0;
    const usdc = chain.tokens.find((t) => t.symbol === 'USDC');
    return usdc?.balance ?? 0;
  };

  return {
    balances,
    isLoading,
    error,
    refetch: fetchBalances,
    solUsdc: getUsdc(balances?.solana ?? null),
    arbUsdc: getUsdc(balances?.arbitrum ?? null),
    solBalance: balances?.solana?.native_balance ?? 0,
    ethBalance: balances?.arbitrum?.native_balance ?? 0,
    hlBalance: balances?.hyperliquid_clearinghouse ?? 0,
  };
}
