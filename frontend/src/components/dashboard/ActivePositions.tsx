import { useEffect, useState } from 'react';
import { usePrivy } from '@privy-io/react-auth';
import { usePositionsStore, useUIStore } from '../../stores';
import { usePositions } from '../../hooks';
import type { Position } from '../../stores';
import { PositionCard } from '../positions/PositionCard';
import { ClosePositionModal } from '../positions/ClosePositionModal';

export function ActivePositions() {
  const { authenticated } = usePrivy();
  const { fetchPositions } = usePositions();
  const positions = usePositionsStore((s) => s.positions);
  const isLoading = usePositionsStore((s) => s.isLoading);
  const { openModal, closeModal, activeModal } = useUIStore();
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);

  useEffect(() => {
    if (authenticated) {
      fetchPositions();
    }
  }, [authenticated, fetchPositions]);

  const openPositions = positions.filter((p) => p.status === 'open');

  const handleClosePosition = (position: Position) => {
    setSelectedPosition(position);
    openModal('closePosition');
  };

  const handleCloseModal = () => {
    closeModal();
    setSelectedPosition(null);
  };

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-medium">Active Positions</h2>
        <button
          onClick={fetchPositions}
          disabled={isLoading}
          className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1 disabled:opacity-50"
        >
          <svg className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>

      {!authenticated ? (
        <div className="text-center py-8 text-gray-500">
          <p>Connect wallet to view positions</p>
        </div>
      ) : openPositions.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <p>No active positions</p>
          <p className="text-sm mt-1">Select leverage and click &quot;Open Position&quot; to start</p>
        </div>
      ) : (
        <div className="divide-y divide-gray-700">
          {openPositions.map((position) => (
            <PositionCard
              key={position.id}
              position={position}
              onClose={() => handleClosePosition(position)}
            />
          ))}
        </div>
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
