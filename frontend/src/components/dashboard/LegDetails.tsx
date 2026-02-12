import { useRates } from '../../hooks';

interface LegDetailsProps {
  leverage: number;
}

function RateRow({ label, value, color, suffix = '%' }: {
  label: string;
  value: string;
  color?: string;
  suffix?: string;
}) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-400">{label}</span>
      <span className={color ?? 'text-white'}>{value}{suffix}</span>
    </div>
  );
}

export function LegDetails({ leverage }: LegDetailsProps) {
  const { rates, isLoading } = useRates(leverage);
  const raw = rates?.raw;

  // Asgard details (best protocol)
  const details = raw?.asgard_details;
  const bestAsgard = raw?.asgard
    ? Object.entries(raw.asgard).reduce((a, b) => (a[1] > b[1] ? a : b), ['—', 0])
    : null;
  const asgardProtocol = bestAsgard ? bestAsgard[0] : '—';

  // HL rates
  const hl = raw?.hyperliquid;

  // HL sign convention: negative = shorts get paid (good for us)
  // We show from short's perspective: negate the sign so positive = earning
  const hlBaseAnn = hl?.base_annualized ?? 0;
  const hlLevAnn = hl?.annualized ?? 0;
  const shortsEarnBase = -hlBaseAnn;
  const shortsEarnLev = -hlLevAnn;

  // Color: green if shorts earn (positive after negate), red if shorts pay
  const hlColor = (v: number) => v >= 0 ? 'text-green-400' : 'text-red-400';
  const hlSign = (v: number) => v >= 0 ? '+' : '';

  // Asgard net color
  const asgardNetColor = (details?.net_apy ?? 0) >= 0 ? 'text-green-400' : 'text-red-400';

  const fmt = (v: number | undefined, decimals = 2) =>
    v !== undefined ? v.toFixed(decimals) : '—';

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <h2 className="text-lg font-medium mb-4">Position Legs</h2>
      <div className="grid md:grid-cols-2 gap-4">
        {/* Asgard Long Leg */}
        <div className="bg-gray-700/50 p-4 rounded-lg">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-2xl">⚡</span>
            <div>
              <h3 className="font-medium">Asgard (Solana)</h3>
              <p className="text-xs text-gray-400">Long Position via {isLoading ? '...' : asgardProtocol}</p>
            </div>
          </div>
          <div className="space-y-2 text-sm">
            <RateRow
              label="Base lending rate"
              value={isLoading ? '...' : fmt(details?.base_lending_apy)}
              color="text-blue-300"
            />
            <RateRow
              label="Leverage"
              value={isLoading ? '...' : leverage.toFixed(1)}
              suffix="x"
            />
            <RateRow
              label="Net lending rate"
              value={isLoading ? '...' : `+${fmt(details?.lending_apy)}`}
              color="text-green-400"
            />
            <RateRow
              label="Borrow cost"
              value={isLoading ? '...' : `-${fmt(details?.borrowing_apy)}`}
              color="text-red-400"
            />
            <div className="border-t border-gray-600 pt-2 mt-2">
              <RateRow
                label="Net APY (long)"
                value={isLoading ? '...' : `${(details?.net_apy ?? 0) >= 0 ? '+' : ''}${fmt(details?.net_apy)}`}
                color={asgardNetColor}
              />
            </div>
          </div>
        </div>

        {/* Hyperliquid Short Leg */}
        <div className="bg-gray-700/50 p-4 rounded-lg">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-2xl">📉</span>
            <div>
              <h3 className="font-medium">Hyperliquid</h3>
              <p className="text-xs text-gray-400">Short Position (SOL-PERP)</p>
            </div>
          </div>
          <div className="space-y-2 text-sm">
            <RateRow
              label="Base funding rate"
              value={isLoading ? '...' : `${hlSign(shortsEarnBase)}${fmt(Math.abs(hlBaseAnn))}`}
              color={hlColor(shortsEarnBase)}
            />
            <div className="flex justify-between">
              <span className="text-gray-400"></span>
              <span className="text-xs text-gray-500">
                {isLoading ? '' : shortsEarnBase >= 0 ? 'shorts earn' : 'shorts pay'}
              </span>
            </div>
            <RateRow
              label="Leverage"
              value={isLoading ? '...' : leverage.toFixed(1)}
              suffix="x"
            />
            <div className="border-t border-gray-600 pt-2 mt-2">
              <RateRow
                label="Net funding (on capital)"
                value={isLoading ? '...' : `${hlSign(shortsEarnLev)}${fmt(Math.abs(hlLevAnn))}`}
                color={hlColor(shortsEarnLev)}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
