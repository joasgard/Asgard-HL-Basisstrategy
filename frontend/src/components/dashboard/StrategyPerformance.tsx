import { useRates } from '../../hooks';

interface StrategyPerformanceProps {
  leverage: number;
}

export function StrategyPerformance({ leverage }: StrategyPerformanceProps) {
  const { rates, isLoading } = useRates(leverage);

  const raw = rates?.raw;
  const bestProtocol = raw?.combined
    ? Object.entries(raw.combined).reduce((a, b) => (a[1] > b[1] ? a : b), ['—', 0])
    : null;
  const netApy = bestProtocol ? bestProtocol[1].toFixed(2) : '—';
  const protocol = bestProtocol ? bestProtocol[0] : '—';
  const hlAnnualized = raw?.hyperliquid?.annualized ?? 0;
  // Negate: in HL convention, negative = shorts earn. Show from short's perspective.
  const shortsEarn = -hlAnnualized;
  const fundingDisplay = Math.abs(hlAnnualized).toFixed(2);
  const fundingColor = shortsEarn >= 0 ? 'text-green-400' : 'text-red-400';
  const fundingLabel = shortsEarn >= 0 ? 'earned by shorts' : 'paid by shorts';
  const asgardNetApy = raw?.asgard_details?.net_apy?.toFixed(2) ?? '—';

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-medium">Strategy Performance</h2>
        <span className="text-xs text-gray-500">
          {isLoading ? 'Updating...' : `Net APY @ ${leverage.toFixed(1)}x`}
        </span>
      </div>

      <div className="p-6 bg-gradient-to-r from-[#081631]/70 to-[#133e78]/50 border border-[#cbd5e1]/13 rounded-xl text-center">
        <div className="text-sm text-blue-300 mb-2">Combined Net APY</div>
        <div className="text-5xl font-bold text-white mb-2">
          {isLoading ? '...' : `${netApy}%`}
        </div>
        <div className="text-sm text-gray-400">via {protocol}</div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
        <div className="bg-gray-700/50 p-3 rounded-lg">
          <div className="text-gray-400">HL Funding (annualized)</div>
          <div className={`${fundingColor} font-medium`}>
            {isLoading ? '...' : `${shortsEarn >= 0 ? '+' : '-'}${fundingDisplay}%`}
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            {isLoading ? '' : fundingLabel}
          </div>
        </div>
        <div className="bg-gray-700/50 p-3 rounded-lg">
          <div className="text-gray-400">Asgard Net APY</div>
          <div className="text-blue-400 font-medium">
            {isLoading ? '...' : `${asgardNetApy}%`}
          </div>
        </div>
      </div>
    </div>
  );
}
