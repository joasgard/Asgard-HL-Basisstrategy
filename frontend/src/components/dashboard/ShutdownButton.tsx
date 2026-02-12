import { useState } from 'react';
import { usePositionsStore, useUIStore } from '../../stores';
import { usePositions } from '../../hooks';

export function ShutdownButton() {
  const positions = usePositionsStore((state) => state.positions);
  const { closePosition } = usePositions();
  const { setGlobalLoading } = useUIStore();
  const [confirming, setConfirming] = useState(false);

  const openPositions = positions.filter((p) => p.status === 'open');
  const hasOpenPositions = openPositions.length > 0;

  const handleShutdown = async () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }

    setConfirming(false);
    setGlobalLoading(true, 'Shutting down all positions...');

    try {
      for (const position of openPositions) {
        await closePosition(position.id);
      }
    } catch (error) {
      console.error('Shutdown error:', error);
    } finally {
      setGlobalLoading(false);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center">
      <button
        onClick={handleShutdown}
        onBlur={() => setConfirming(false)}
        disabled={!hasOpenPositions}
        className={`w-full h-full min-h-[80px] py-3 rounded-xl font-bold text-lg transition-colors flex flex-col items-center justify-center gap-2 ${
          confirming
            ? 'bg-red-700 hover:bg-red-800'
            : 'bg-red-600/80 hover:bg-red-700 disabled:bg-gray-600 disabled:cursor-not-allowed'
        }`}
      >
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
        </svg>
        <span>{confirming ? 'Confirm Shut Down' : 'Shut Down'}</span>
        {hasOpenPositions && !confirming && (
          <span className="text-xs font-normal opacity-70">{openPositions.length} open position{openPositions.length !== 1 ? 's' : ''}</span>
        )}
      </button>
    </div>
  );
}
