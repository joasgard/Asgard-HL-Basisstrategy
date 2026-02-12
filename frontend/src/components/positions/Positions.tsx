import { useEffect, useMemo, useState } from 'react';
import { usePrivy } from '@privy-io/react-auth';
import { usePositions } from '../../hooks';
import { usePositionsStore, useUIStore } from '../../stores';
import type { Position } from '../../stores';
import { PositionCard } from './PositionCard';
import { OpenPositionModal } from './OpenPositionModal';
import { ClosePositionModal } from './ClosePositionModal';
import { SkeletonStats, SkeletonCard } from '../ui';

export function Positions() {
  const { authenticated } = usePrivy();
  const { fetchPositions } = usePositions();
  
  // Subscribe to store state directly in component
  const positions = usePositionsStore((state) => state.positions);
  const isLoading = usePositionsStore((state) => state.isLoading);
  const error = usePositionsStore((state) => state.error);
  const totalPnl = usePositionsStore((state) => state.totalPnl);
  const totalValue = usePositionsStore((state) => state.totalValue);
  const openPositionsCount = usePositionsStore((state) => state.openPositionsCount);
  
  const { openModal, closeModal, activeModal } = useUIStore();
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);

  // Fetch positions once on mount when authenticated
  useEffect(() => {
    if (authenticated) {
      fetchPositions();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authenticated]); // Only run when auth state changes

  const openPositions = useMemo(() => positions.filter((p: Position) => p.status === 'open'), [positions]);

  const handleOpenPosition = () => {
    openModal('openPosition');
  };

  const handleClosePosition = (position: Position) => {
    setSelectedPosition(position);
    openModal('closePosition');
  };

  const handleCloseModal = () => {
    closeModal();
    setSelectedPosition(null);
  };

  // Show connect prompt when not authenticated
  if (!authenticated) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Positions</h1>
        </div>
        
        <div className="bg-blue-900/30 border border-blue-700 rounded-xl p-8 text-center">
          <h2 className="text-xl font-semibold text-blue-400 mb-2">Connect to View Positions</h2>
          <p className="text-gray-400 mb-4">Please connect your wallet to view and manage your positions.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Positions</h1>
        <button
          onClick={handleOpenPosition}
          className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg font-medium transition-colors"
        >
          + Open Position
        </button>
      </div>

      {/* Stats Summary */}
      {isLoading && openPositions.length === 0 ? (
        <SkeletonStats />
      ) : (
        <div className="grid md:grid-cols-4 gap-4">
          <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
            <p className="text-sm text-gray-400">Open Positions</p>
            <p className="text-2xl font-bold">{openPositionsCount}</p>
          </div>
          <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
            <p className="text-sm text-gray-400">Total PnL</p>
            <p className={`text-2xl font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
            </p>
          </div>
          <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
            <p className="text-sm text-gray-400">Total Value</p>
            <p className="text-2xl font-bold">${totalValue.toLocaleString()}</p>
          </div>
          <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
            <p className="text-sm text-gray-400">Avg Leverage</p>
            <p className="text-2xl font-bold">
              {openPositions.length > 0
                ? (openPositions.reduce((sum: number, p: Position) => sum + p.leverage, 0) / openPositions.length).toFixed(1)
                : '0.0'}x
            </p>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 flex items-center gap-3">
          <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-red-200">{error}</p>
          <button
            onClick={fetchPositions}
            className="ml-auto text-sm text-red-400 hover:text-red-300 underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Positions List */}
      <div className="bg-gray-800 rounded-xl border border-gray-700">
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <h2 className="text-lg font-medium">Active Positions</h2>
          <button
            onClick={fetchPositions}
            disabled={isLoading}
            className="text-sm text-gray-400 hover:text-white flex items-center gap-1 disabled:opacity-50"
          >
            <svg className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>

        {isLoading && openPositions.length === 0 ? (
          <div className="p-4 space-y-4">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : openPositions.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            <p>No active positions</p>
            <p className="text-sm mt-1">Click &quot;Open Position&quot; to start trading</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-700">
            {openPositions.map((position: Position) => (
              <PositionCard
                key={position.id}
                position={position}
                onClose={() => handleClosePosition(position)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Modals */}
      {activeModal === 'openPosition' && (
        <OpenPositionModal onClose={handleCloseModal} />
      )}

      {activeModal === 'closePosition' && selectedPosition && (
        <ClosePositionModal
          position={selectedPosition}
          onClose={handleCloseModal}
        />
      )}
    </div>
  );
}
