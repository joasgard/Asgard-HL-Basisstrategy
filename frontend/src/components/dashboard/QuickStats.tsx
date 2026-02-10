export function QuickStats() {
  // TODO: Fetch actual stats from API
  const stats = {
    positions: 0,
    pnl24h: '$0.00',
    totalValue: '$0.00',
  };

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <h2 className="text-lg font-medium mb-4">📊 Quick Stats</h2>
      <div className="space-y-3">
        <div className="flex justify-between">
          <span className="text-gray-400">Open Positions</span>
          <span className="font-mono">{stats.positions}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">24h PnL</span>
          <span className="font-mono">{stats.pnl24h}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Total Value</span>
          <span className="font-mono">{stats.totalValue}</span>
        </div>
      </div>
    </div>
  );
}
