import { useState, useCallback } from 'react';
import { usePositions } from '../../hooks';
import { useSettingsStore } from '../../stores';
import { LoadingSpinner } from '../ui';
import { PreflightChecklist } from './PreflightChecklist';
import type { OpenPositionRequest } from '../../api/positions';

interface OpenPositionModalProps {
  onClose: () => void;
  defaultLeverage?: number;
}

// Transaction costs (in basis points, 1 bp = 0.01%)
const TX_COSTS = {
  asgardOpen: 15,       // 0.15% - LST swap + deposit (flat fee)
  hyperliquidOpen: 3.5, // 0.035% - perp taker fee on open (market order)
};

export function OpenPositionModal({ onClose, defaultLeverage }: OpenPositionModalProps) {
  const minPositionSize = useSettingsStore((state) => state.minPositionSize);
  const maxPositionSize = useSettingsStore((state) => state.maxPositionSize);
  const defaultLeverageSetting = useSettingsStore((state) => state.defaultLeverage);
  const { openPosition } = usePositions();

  const asset = 'SOL';
  const [leverage, setLeverage] = useState(defaultLeverage ?? defaultLeverageSetting);
  const [size, setSize] = useState(1000);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPreflight, setShowPreflight] = useState(false);
  const [preflightRequest, setPreflightRequest] = useState<OpenPositionRequest | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const req: OpenPositionRequest = { asset, leverage, size_usd: size };
    setPreflightRequest(req);
    setShowPreflight(true);
    setIsSubmitting(true);
  };

  const handlePreflightPassed = useCallback(async () => {
    try {
      await openPosition(asset, leverage, size);
      onClose();
    } catch (error) {
      console.error('Failed to open position:', error);
    } finally {
      setIsSubmitting(false);
    }
  }, [asset, leverage, size, openPosition, onClose]);

  const handlePreflightDismiss = useCallback(() => {
    setShowPreflight(false);
    setPreflightRequest(null);
    setIsSubmitting(false);
  }, []);

  // Calculate position with transaction costs for delta neutrality
  // To be delta neutral, we need: Long Exposure = Short Exposure after fees
  // If we deploy $X to Asgard and $Y to Hyperliquid:
  // Asgard effective long = X * (1 - asgard_fee)
  // Hyperliquid effective short = Y * (1 - hyperliquid_fee)
  // For delta neutral: X * (1 - asgard_fee) = Y * (1 - hyperliquid_fee)
  // With total capital = X + Y = size
  
  const asgardFeeRate = TX_COSTS.asgardOpen / 10000;
  const hlFeeRate = TX_COSTS.hyperliquidOpen / 10000;
  
  // Solve for allocation that results in equal exposure after fees
  // X * (1 - asgardFee) = (size - X) * (1 - hlFee)
  // X * (1 - asgardFee + 1 - hlFee) = size * (1 - hlFee)
  // X = size * (1 - hlFee) / (2 - asgardFee - hlFee)
  const totalFeeFactor = 2 - asgardFeeRate - hlFeeRate;
  const asgardAllocation = (size * (1 - hlFeeRate)) / totalFeeFactor;
  const hyperliquidAllocation = size - asgardAllocation;
  
  // Effective exposures after fees
  const asgardEffectiveLong = asgardAllocation * (1 - asgardFeeRate);
  const hyperliquidEffectiveShort = hyperliquidAllocation * (1 - hlFeeRate);
  
  // Transaction costs
  const asgardTxCost = asgardAllocation * asgardFeeRate;
  const hyperliquidTxCost = hyperliquidAllocation * hlFeeRate;
  const totalTxCost = asgardTxCost + hyperliquidTxCost;
  
  // Net delta exposure (should be near zero)
  const netDeltaExposure = asgardEffectiveLong - hyperliquidEffectiveShort;
  
  // Total position value at leverage
  const totalPosition = size * leverage;

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-xl max-w-md w-full border border-gray-700">
        {/* Header */}
        <div className="p-6 border-b border-gray-700">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold">Open SOL Position</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-white">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Leverage */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">Leverage ({leverage.toFixed(1)}x)</label>
            <input
              type="range"
              min="1.1"
              max="4"
              step="0.1"
              value={leverage}
              onChange={(e) => setLeverage(parseFloat(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>1.1x</span>
              <span>4x</span>
            </div>
          </div>

          {/* Size */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">Size (USD)</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">$</span>
              <input
                type="number"
                value={size}
                onChange={(e) => setSize(parseInt(e.target.value))}
                className="w-full pl-8 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg"
                min={minPositionSize}
                max={maxPositionSize}
                step="100"
              />
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Min: ${minPositionSize} | Max: ${maxPositionSize.toLocaleString()}
            </p>
          </div>

          {/* Summary */}
          <div className="bg-gray-700/50 rounded-lg p-4 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Asgard Long</span>
              <span>${asgardAllocation.toFixed(2)}</span>
            </div>
            <div className="text-xs text-gray-500 text-right">
              -${asgardTxCost.toFixed(2)} tx cost
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Hyperliquid Short</span>
              <span>${hyperliquidAllocation.toFixed(2)}</span>
            </div>
            <div className="text-xs text-gray-500 text-right">
              -${hyperliquidTxCost.toFixed(2)} tx cost
            </div>
            <div className="flex justify-between text-xs text-gray-500 pt-2 border-t border-gray-600">
              <span>Net Delta Exposure</span>
              <span className={Math.abs(netDeltaExposure) < 1 ? 'text-green-400' : 'text-yellow-400'}>
                ${netDeltaExposure.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between text-xs text-gray-500">
              <span>Total Transaction Costs</span>
              <span>${totalTxCost.toFixed(2)} ({((totalTxCost/size)*100).toFixed(2)}%)</span>
            </div>
            <div className="flex justify-between text-sm pt-2 border-t border-gray-600">
              <span className="text-gray-400">Total Position</span>
              <span className="font-bold">${totalPosition.toLocaleString()}</span>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg font-medium transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || size < minPositionSize || size > maxPositionSize}
              className="flex-1 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <LoadingSpinner size="sm" />
                  Opening...
                </>
              ) : (
                'Confirm'
              )}
            </button>
          </div>
        </form>
      </div>

      {showPreflight && preflightRequest && (
        <PreflightChecklist
          request={preflightRequest}
          onAllPassed={handlePreflightPassed}
          onDismiss={handlePreflightDismiss}
        />
      )}
    </div>
  );
}
