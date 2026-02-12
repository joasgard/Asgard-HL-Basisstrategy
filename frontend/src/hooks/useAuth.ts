import { usePrivy, useWallets } from '@privy-io/react-auth';
import { useEffect, useState, useCallback, useRef } from 'react';
import { useAuthStore } from '../stores';
import * as authApi from '../api/auth';
import { walletSetupApi } from '../api/walletSetup';

export function useAuth() {
  const {
    ready,
    authenticated,
    user: privyUser,
    login,
    logout: privyLogout,
    createWallet,
    getAccessToken,
  } = usePrivy();
  const { wallets } = useWallets();

  const { setUser, setAuthenticated, setLoading, logout: storeLogout } = useAuthStore();
  const [backendSynced, setBackendSynced] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const isSyncingRef = useRef(false);

  // Sync Privy auth with backend session
  const syncWithBackend = useCallback(async () => {
    if (!authenticated || !privyUser) {
      setBackendSynced(false);
      return;
    }

    // Prevent duplicate syncs
    if (isSyncingRef.current) return;

    try {
      isSyncingRef.current = true;
      setSyncError(null);

      // First check if we already have a valid session
      const status = await authApi.checkAuthStatus();

      if (status.authenticated && status.user) {
        // Backend session exists - sync user data
        setUser({
          id: status.user.user_id,
          email: status.user.email,
          wallets: [], // Will be populated from Privy wallets below
        });

        // Ensure both wallets exist even for existing sessions
        // (covers the case where Solana wallet was missing on initial signup)
        if (!status.user.solana_address || !status.user.evm_address) {
          try {
            await walletSetupApi.ensureWallets();
          } catch (e) {
            console.warn('Failed to ensure wallets:', e);
          }
        }

        setBackendSynced(true);
        return;
      }

      // No backend session - create one via sync endpoint
      const accessToken = await getAccessToken();
      if (!accessToken) {
        throw new Error('Failed to get Privy access token');
      }

      const syncResult = await authApi.syncPrivyAuth(
        accessToken,
        privyUser.email?.address
      );

      if (syncResult.success) {
        setUser({
          id: syncResult.user_id,
          email: syncResult.email,
          wallets: [],
        });

        // After sync, ensure both wallets exist on the backend.
        // The sync endpoint already tries, but the Privy frontend SDK may
        // still be provisioning the Solana wallet asynchronously. This
        // second call catches that race condition.
        if (!syncResult.solana_address || !syncResult.evm_address) {
          try {
            await walletSetupApi.ensureWallets();
          } catch (e) {
            console.warn('Failed to ensure wallets after sync:', e);
          }
        }

        setBackendSynced(true);
      }
    } catch (error) {
      console.error('Failed to sync with backend:', error);
      setSyncError('Backend connection failed');
      setBackendSynced(false);
    } finally {
      isSyncingRef.current = false;
    }
  }, [authenticated, privyUser, setUser, getAccessToken]);

  // Sync with backend when auth state changes
  useEffect(() => {
    if (ready && authenticated && privyUser) {
      syncWithBackend();
    }
  }, [ready, authenticated, privyUser?.id, syncWithBackend]);

  // Sync Privy state with our store
  useEffect(() => {
    setLoading(!ready);

    if (ready) {
      setAuthenticated(authenticated);

      if (authenticated && privyUser) {
        // Map EVM embedded wallets from useWallets() hook
        // useWallets() only returns EVM wallets, so chainType is always 'ethereum'
        const embeddedWallets = wallets
          .filter(w => w.walletClientType === 'privy')
          .map(w => ({
            address: w.address,
            chainType: 'ethereum' as const,
            type: 'embedded' as const,
          }));

        // Solana wallets appear in user.linkedAccounts, not in useWallets()
        const solanaAccounts = privyUser.linkedAccounts?.filter(
          (a: any) => a.type === 'wallet' && a.chainType === 'solana'
        ) || [];

        const solanaWallets = solanaAccounts.map((a: any) => ({
          address: a.address,
          chainType: 'solana' as const,
          type: 'embedded' as const,
        }));

        setUser({
          id: privyUser.id,
          email: privyUser.email?.address,
          wallets: [...embeddedWallets, ...solanaWallets],
        });
      } else {
        setUser(null);
      }
    }
  }, [ready, authenticated, privyUser, wallets, setUser, setAuthenticated, setLoading]);

  const logout = async () => {
    try {
      // Logout from backend first (clears session cookie)
      await authApi.logoutBackend();
    } catch (error) {
      console.error('Backend logout error:', error);
    }
    // Always logout from Privy
    await privyLogout();
    storeLogout();
    setBackendSynced(false);
  };

  const ensureSolanaWallet = async () => {
    // Check if user has a Solana wallet in linked accounts
    const solanaAccount = privyUser?.linkedAccounts?.find(
      (a: any) => a.type === 'wallet' && a.chainType === 'solana'
    );
    
    if (!solanaAccount) {
      // Create Solana wallet using the createWallet from usePrivy
      // Note: This may not work for Solana, server-side creation might be needed
      return await createWallet({ chainType: 'solana' } as Parameters<typeof createWallet>[0]);
    }
    return solanaAccount;
  };

  return {
    isReady: ready,
    isAuthenticated: authenticated,
    isLoading: !ready,
    isSyncing: isSyncingRef.current,
    backendSynced,
    syncError,
    user: privyUser,
    wallets,
    login,
    logout,
    createWallet,
    ensureSolanaWallet,
    retrySync: syncWithBackend,
  };
}
