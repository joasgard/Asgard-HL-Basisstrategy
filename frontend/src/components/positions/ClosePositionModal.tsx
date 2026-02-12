import { useState } from 'react';
import { usePositions } from '../../hooks';
import type { Position } from '../../stores';
import { useUIStore } from '../../stores';
import { LoadingSpinner } from '../ui';

interface ClosePositionModalProps {
  position: Position;
  onClose: () => void;
}

export function ClosePositionModal({ position, onClose }: ClosePositionModalProps) {
  const { closePosition } = usePositions();
  const { setGlobalLoading } = useUIStore();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setGlobalLoading(true, 'Closing position...');

    try {
      await closePosition(position.id);
      onClose();
    } catch (error) {
      console.error('Failed to close position:', error);
    } finally {
      setIsSubmitting(false);
      setGlobalLoading(false);
    }
  };

  const pnlColor = position.pnl_usd >= 0 ? 'text-green-400' : 'text-red-400';

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-xl max-w-md w-full border border-gray-700">
        {/* Header */}
        <div className="p-6 border-b border-gray-700">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold">Close Position</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-white">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {/* Warning */}
          <div className="bg-yellow-900/30 border border-yellow-700/50 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <svg
                className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <div>
                <h3 className="font-medium text-yellow-200">Confirm Position Closure</h3>
                <p className="text-sm text-yellow-200/70 mt-1">
                  This will close both your Asgard long and Hyperliquid short positions. This action
                  cannot be undone.
                </p>
              </div>
            </div>
          </div>

          {/* Position Details */}
          <div className="bg-gray-700/50 rounded-lg p-4 space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-400">Asset</span>
              <span className="font-medium">{position.asset}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Size</span>
              <span className="font-medium">${position.size_usd.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Leverage</span>
              <span className="font-medium">{position.leverage}x</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Entry Price</span>
              <span className="font-medium">${position.entry_price.toFixed(2)}</span>
            </div>
            <div className="flex justify-between pt-3 border-t border-gray-600">
              <span className="text-gray-400">PnL</span>
              <span className={`font-bold ${pnlColor}`}>
                {position.pnl_usd >= 0 ? '+' : ''}${position.pnl_usd.toFixed(2)}
              </span>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={onClose}
              className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg font-medium transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="flex-1 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <LoadingSpinner size="sm" />
                  Closing...
                </>
              ) : (
                'Close Position'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
