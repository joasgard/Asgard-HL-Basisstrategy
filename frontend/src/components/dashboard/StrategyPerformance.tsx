interface StrategyPerformanceProps {
  leverage: number;
}

export function StrategyPerformance({ leverage }: StrategyPerformanceProps) {
  // TODO: Fetch actual rates from API
  const netApy = (12.5 * leverage).toFixed(2);
  const protocol = 'Kamino';

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-medium">🎯 Strategy Performance</h2>
        <span className="text-xs text-gray-500">Net APY @ {leverage.toFixed(1)}x</span>
      </div>

      <div className="p-6 bg-gradient-to-r from-blue-900/50 to-purple-900/50 border border-blue-700/50 rounded-xl text-center">
        <div className="text-sm text-blue-300 mb-2">Net APY</div>
        <div className="text-5xl font-bold text-white mb-2">{netApy}%</div>
        <div className="text-sm text-gray-400">via {protocol} Protocol</div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
        <div className="bg-gray-700/50 p-3 rounded-lg">
          <div className="text-gray-400">Funding Rate</div>
          <div className="text-green-400 font-medium">-8.5% APY</div>
        </div>
        <div className="bg-gray-700/50 p-3 rounded-lg">
          <div className="text-gray-400">Net Carry</div>
          <div className="text-blue-400 font-medium">+4.2% APY</div>
        </div>
      </div>
    </div>
  );
}
