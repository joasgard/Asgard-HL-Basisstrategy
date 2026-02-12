import { useEffect } from 'react';
import { usePrivy } from '@privy-io/react-auth';
import { usePositionsStore } from '../../stores';
import { usePositions, useBalances } from '../../hooks';

export function QuickStats() {
  const { authenticated } = usePrivy();
  const { fetchPositions } = usePositions();
  const { balances, isLoading: balancesLoading, solBalance, solUsdc, ethBalance, arbUsdc, hlBalance, refetch: refetchBalances } = useBalances();
  const totalPnl = usePositionsStore((s) => s.totalPnl);
  const totalValue = usePositionsStore((s) => s.totalValue);
  const openPositionsCount = usePositionsStore((s) => s.openPositionsCount);

  useEffect(() => {
    if (authenticated) {
      fetchPositions();
    }
  }, [authenticated, fetchPositions]);

  const fmt = (v: number, decimals = 2) => v.toFixed(decimals);
  const loading = balancesLoading ? '...' : null;

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-medium">Quick Stats</h2>
        {authenticated && (
          <button
            onClick={refetchBalances}
            disabled={balancesLoading}
            className="text-gray-400 hover:text-white disabled:opacity-50 transition-colors"
            title="Refresh balances"
          >
            <svg
              className={`w-4 h-4 ${balancesLoading ? 'animate-spin' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </button>
        )}
      </div>
      <div className="space-y-3">
        <div className="flex justify-between">
          <span className="text-gray-400">Open Positions</span>
          <span className="font-mono">{authenticated ? openPositionsCount : '—'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Total PnL</span>
          <span className={`font-mono ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {authenticated ? `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}` : '—'}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Total Value</span>
          <span className="font-mono">
            {authenticated ? `$${totalValue.toLocaleString()}` : '—'}
          </span>
        </div>
      </div>

      {/* Wallet Balances */}
      {authenticated && (
        <>
          <div className="border-t border-gray-700 my-4" />
          <h3 className="text-sm font-medium text-gray-300 mb-3">Wallet Balances</h3>
          <div className="space-y-2 text-sm">
            {/* Solana */}
            <div className="bg-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 mb-1.5">Solana</div>
              <div className="flex justify-between">
                <span className="text-gray-400">SOL</span>
                <span className="font-mono text-green-400">
                  {loading ?? fmt(solBalance, 4)}
                </span>
              </div>
              <div className="flex justify-between mt-1">
                <span className="text-gray-400">USDC</span>
                <span className="font-mono text-green-400">
                  {loading ?? `$${fmt(solUsdc)}`}
                </span>
              </div>
            </div>

            {/* Arbitrum */}
            <div className="bg-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 mb-1.5">Arbitrum</div>
              <div className="flex justify-between">
                <span className="text-gray-400">ETH</span>
                <span className="font-mono text-blue-400">
                  {loading ?? fmt(ethBalance, 4)}
                </span>
              </div>
              <div className="flex justify-between mt-1">
                <span className="text-gray-400">USDC</span>
                <span className="font-mono text-blue-400">
                  {loading ?? `$${fmt(arbUsdc)}`}
                </span>
              </div>
            </div>

            {/* Hyperliquid */}
            <div className="flex justify-between bg-gray-700/50 rounded-lg p-3">
              <div>
                <div className="text-xs text-gray-500 mb-1">Hyperliquid</div>
                <span className="text-gray-400">Clearinghouse</span>
              </div>
              <span className="font-mono text-purple-400 self-end">
                {loading ?? `$${fmt(hlBalance)}`}
              </span>
            </div>

            {/* Total */}
            {balances?.total_usd_value != null && (
              <div className="flex justify-between pt-2 border-t border-gray-700">
                <span className="text-gray-300 font-medium">Total</span>
                <span className="font-mono text-white font-medium">
                  ${fmt(balances.total_usd_value)}
                </span>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
