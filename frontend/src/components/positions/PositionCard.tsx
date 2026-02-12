import type { Position } from '../../stores';

interface PositionCardProps {
  position: Position;
  onClose: () => void;
}

export function PositionCard({ position, onClose }: PositionCardProps) {
  const pnlColor = position.pnl_usd >= 0 ? 'text-green-400' : 'text-red-400';
  const healthColor = 
    position.health_factor > 0.2 ? 'text-green-400' :
    position.health_factor > 0.1 ? 'text-yellow-400' : 'text-red-400';

  return (
    <div className="p-4 hover:bg-gray-700/50 transition-colors">
      <div className="flex items-center justify-between">
        {/* Left: Asset & Size */}
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-gray-700 rounded-lg flex items-center justify-center text-xl">
            {position.asset === 'SOL' ? '⚡' : position.asset === 'jitoSOL' ? '📈' : '💎'}
          </div>
          <div>
            <h3 className="font-medium text-white">{position.asset}</h3>
            <p className="text-sm text-gray-400">
              {position.leverage}x leverage • ${position.size_usd.toLocaleString()}
            </p>
          </div>
        </div>

        {/* Middle: PnL */}
        <div className="text-right">
          <p className={`text-lg font-bold ${pnlColor}`}>
            {position.pnl_usd >= 0 ? '+' : ''}${position.pnl_usd.toFixed(2)}
          </p>
          <p className={`text-sm ${pnlColor}`}>
            {position.pnl_percent >= 0 ? '+' : ''}{position.pnl_percent.toFixed(2)}%
          </p>
        </div>

        {/* Right: Health & Actions */}
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-sm text-gray-400">Health</p>
            <p className={`font-medium ${healthColor}`}>
              {(position.health_factor * 100).toFixed(0)}%
            </p>
          </div>
          
          <button
            onClick={onClose}
            className="px-4 py-2 bg-red-600/80 hover:bg-red-600 rounded-lg text-sm font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>

      {/* Expanded Details (always visible for now) */}
      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-gray-500">Entry Price</p>
          <p className="font-mono">${position.entry_price.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-gray-500">Current Price</p>
          <p className="font-mono">${position.current_price.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-gray-500">Asgard PDA</p>
          <p className="font-mono text-xs truncate">{position.asgard_pda}</p>
        </div>
        <div>
          <p className="text-gray-500">Opened</p>
          <p className="font-mono text-xs">
            {new Date(position.created_at).toLocaleDateString()}
          </p>
        </div>
      </div>
    </div>
  );
}
