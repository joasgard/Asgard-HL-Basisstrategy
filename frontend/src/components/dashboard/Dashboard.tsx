import { useState } from 'react';
import { LeverageSlider } from './LeverageSlider';
import { OpenPositionButton } from './OpenPositionButton';
import { StrategyPerformance } from './StrategyPerformance';
import { QuickStats } from './QuickStats';
import { LegDetails } from './LegDetails';
import { ActivePositions } from './ActivePositions';

export function Dashboard() {
  const [leverage, setLeverage] = useState(3.0);

  return (
    <div className="space-y-6">
      {/* Leverage Selector + Open Position (Side by Side) */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex flex-col md:flex-row gap-6">
          {/* Left: Leverage Slider (Half Width on Desktop) */}
          <LeverageSlider value={leverage} onChange={setLeverage} />
          
          {/* Right: Open Position Button (Half Width on Desktop) */}
          <OpenPositionButton leverage={leverage} />
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
    </div>
  );
}
