interface LegDetailsProps {
  leverage: number;
}

export function LegDetails({ leverage }: LegDetailsProps) {
  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <h2 className="text-lg font-medium mb-4">Position Legs</h2>
      <div className="grid md:grid-cols-2 gap-4">
        {/* Asgard Leg */}
        <div className="bg-gray-700/50 p-4 rounded-lg">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-2xl">⚡</span>
            <div>
              <h3 className="font-medium">Asgard (Solana)</h3>
              <p className="text-xs text-gray-400">Long Position</p>
            </div>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Protocol</span>
              <span>Kamino</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">APY</span>
              <span className="text-green-400">+12.5%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Leverage</span>
              <span>{leverage.toFixed(1)}x</span>
            </div>
          </div>
        </div>

        {/* Hyperliquid Leg */}
        <div className="bg-gray-700/50 p-4 rounded-lg">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-2xl">📉</span>
            <div>
              <h3 className="font-medium">Hyperliquid</h3>
              <p className="text-xs text-gray-400">Short Position</p>
            </div>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Funding Rate</span>
              <span className="text-green-400">-8.5%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Margin Used</span>
              <span>33%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Leverage</span>
              <span>{leverage.toFixed(1)}x</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
