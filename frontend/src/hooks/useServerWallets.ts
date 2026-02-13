import { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient } from '../api/client';

export interface ServerWallets {
  ready: boolean;
  evm_wallet_id: string | null;
  evm_address: string | null;
  solana_wallet_id: string | null;
  solana_address: string | null;
}

const POLL_INTERVAL_MS = 5000;

/**
 * Fetch and poll server wallet provisioning status.
 *
 * Polls every 5 seconds while `ready` is false, then stops.
 */
export function useServerWallets(authenticated: boolean) {
  const [wallets, setWallets] = useState<ServerWallets | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchWallets = useCallback(async () => {
    if (!authenticated) return;
    try {
      setLoading(true);
      const { data } = await apiClient.get<ServerWallets>('/wallets/server');
      setWallets(data);
      setError(null);

      // Stop polling once ready
      if (data.ready && intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    } catch (e: any) {
      if (e.httpStatus === 401) {
        setWallets(null);
      } else {
        setError(e.message || 'Failed to fetch server wallets');
      }
    } finally {
      setLoading(false);
    }
  }, [authenticated]);

  useEffect(() => {
    fetchWallets();

    if (authenticated) {
      intervalRef.current = setInterval(fetchWallets, POLL_INTERVAL_MS);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [fetchWallets, authenticated]);

  return { wallets, loading, error, refetch: fetchWallets };
}
