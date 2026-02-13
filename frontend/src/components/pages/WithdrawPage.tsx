import { useEffect } from 'react';
import { usePrivy } from '@privy-io/react-auth';
import { useBalances } from '../../hooks';
import { useAuth } from '../../hooks/useAuth';
import { WithdrawModal } from '../modals/WithdrawModal';

export function WithdrawPage() {
  const { ready, authenticated, login, logout, user } = usePrivy();
  const { isLoading, error, solBalance, solUsdc, ethBalance, arbUsdc, hlBalance, refetch } = useBalances();

  // Sync auth with backend so /balances works
  const { backendSynced } = useAuth();

  // Once backend session is established, refetch balances immediately
  // (the initial fetch likely got a 401 before the session cookie was set)
  useEffect(() => {
    if (backendSynced) {
      refetch();
    }
  }, [backendSynced]);

  if (!ready) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <p className="text-gray-400">Initializing Privy...</p>
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div className="min-h-screen bg-gray-900 flex flex-col items-center justify-center gap-4">
        <h1 className="text-2xl font-bold text-white">Withdraw Funds</h1>
        <p className="text-gray-400 text-sm">Connect your account to view balances and withdraw.</p>
        <button
          onClick={login}
          className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg transition-colors"
        >
          Connect
        </button>
      </div>
    );
  }

  const email = user?.email?.address;
  const allZero = solBalance === 0 && solUsdc === 0 && ethBalance === 0 && arbUsdc === 0 && hlBalance === 0;

  return (
    <div className="min-h-screen bg-gray-900 p-4">
      <div className="max-w-md mx-auto pt-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-white">Withdraw Funds</h1>
          <button
            onClick={logout}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            {email || 'Connected'} &middot; Logout
          </button>
        </div>

        {/* Balance summary */}
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-gray-400">Your Balances</h2>
            <button onClick={refetch} className="text-xs text-purple-400 hover:text-purple-300">
              {isLoading ? 'Loading...' : 'Refresh'}
            </button>
          </div>

          {error && (
            <p className="text-xs text-red-400 mb-2">{error}</p>
          )}

          {!backendSynced ? (
            <p className="text-gray-500 text-sm">Syncing session...</p>
          ) : isLoading && allZero ? (
            <p className="text-gray-500 text-sm">Loading balances...</p>
          ) : (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">SOL</span>
                <span className="font-mono text-green-400">{solBalance.toFixed(4)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Solana USDC</span>
                <span className="font-mono text-green-400">${solUsdc.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">ETH</span>
                <span className="font-mono text-blue-400">{ethBalance.toFixed(6)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Arbitrum USDC</span>
                <span className="font-mono text-blue-400">${arbUsdc.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Hyperliquid</span>
                <span className="font-mono text-purple-400">${hlBalance.toFixed(2)}</span>
              </div>
            </div>
          )}
        </div>

        {/* Withdraw modal rendered inline (always open, no close) */}
        <WithdrawModal isOpen={true} onClose={() => {}} />
      </div>
    </div>
  );
}
