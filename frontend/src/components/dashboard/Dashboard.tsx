import { useState } from 'react';
import { usePrivy } from '@privy-io/react-auth';
import { LeverageSlider } from './LeverageSlider';
import { OpenPositionButton } from './OpenPositionButton';
import { ShutdownButton } from './ShutdownButton';
import { StrategyPerformance } from './StrategyPerformance';
import { QuickStats } from './QuickStats';
import { LegDetails } from './LegDetails';
import { ActivePositions } from './ActivePositions';
import { OpenPositionModal } from '../positions/OpenPositionModal';
import { useUIStore } from '../../stores';

export function Dashboard() {
  const { authenticated, login } = usePrivy();
  const { activeModal, closeModal } = useUIStore();
  const [leverage, setLeverage] = useState(3.0);

  return (
    <div className="space-y-6">
      {/* Connect Banner - shown when not authenticated */}
      {!authenticated && (
        <div className="bg-blue-900/30 border border-blue-700 rounded-xl p-6">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-blue-400 mb-1">
                🔐 Connect to Trade
              </h2>
              <p className="text-gray-400 text-sm">
                View live market data and open positions. Connect your wallet to start trading.
              </p>
            </div>
            <button
              onClick={login}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors flex items-center gap-2 whitespace-nowrap"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              Connect Wallet
            </button>
          </div>
        </div>
      )}

      {/* Leverage Selector + Open Position (Side by Side) */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex flex-col md:flex-row gap-6">
          {/* Left: Leverage Slider (Half Width on Desktop) */}
          <LeverageSlider value={leverage} onChange={setLeverage} />
          
          {/* Right: Action Buttons */}
          <div className="flex-1 flex gap-4">
            <OpenPositionButton />
            <ShutdownButton />
          </div>
        </div>
      </div>

      {/* Strategy Performance + Quick Stats */}
      <div className="grid md:grid-cols-2 gap-6">
        <StrategyPerformance leverage={leverage} />
        <QuickStats />
      </div>

      {/* Leg Details */}
      <LegDetails leverage={leverage} />

      {/* Active Positions */}
      <ActivePositions />

      {/* Open Position Modal */}
      {activeModal === 'openPosition' && (
        <OpenPositionModal 
          onClose={closeModal} 
          defaultLeverage={leverage}
        />
      )}
    </div>
  );
}
