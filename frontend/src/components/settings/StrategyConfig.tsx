import { useState, useEffect, useCallback } from 'react';
import { useStrategyConfig } from '../../hooks/useStrategyConfig';
import { strategyApi, RiskStatus } from '../../api/strategy';
import { LoadingSpinner, LabelWithTooltip } from '../ui';

const TOOLTIPS = {
  enabled: 'Enable autonomous trading. The bot will automatically open and close positions based on your settings.',
  minCarryApy: 'Minimum net carry APY (funding + lending - borrowing) required to open a position.',
  maxLeverage: 'Maximum leverage on the Asgard (long) side. Higher = more yield but more liquidation risk.',
  maxPositionPct: 'Maximum % of your balance to deploy in a single position.',
  maxConcurrentPositions: 'Maximum number of positions open at the same time.',
  stopLossPct: 'Automatically close if position loss exceeds this %. Minimum 1%.',
  takeProfitPct: 'Automatically close when profit reaches this %. Set to 0 to disable.',
  minExitCarryApy: 'Close position when carry APY drops below this value.',
  autoReopen: 'After closing a position, automatically reopen when conditions are met again.',
  cooldownMinutes: 'Wait this many minutes after closing before reopening. Minimum 5 minutes.',
  maxFundingVolatility: 'Skip opportunities if funding rate volatility exceeds this (0 = any, 1 = very low).',
};

export function StrategyConfig() {
  const { config, loading, saving, error, save, pause, resume } = useStrategyConfig();

  // Local form state
  const [form, setForm] = useState<Record<string, any>>({});
  const [dirty, setDirty] = useState(false);

  // Risk status
  const [riskStatus, setRiskStatus] = useState<RiskStatus | null>(null);
  const [closingAll, setClosingAll] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  const loadRiskStatus = useCallback(async () => {
    try {
      const status = await strategyApi.getRiskStatus();
      setRiskStatus(status);
    } catch {
      // Non-fatal
    }
  }, []);

  useEffect(() => {
    loadRiskStatus();
    const interval = setInterval(loadRiskStatus, 30_000);
    return () => clearInterval(interval);
  }, [loadRiskStatus]);

  const handleCloseAll = async () => {
    setClosingAll(true);
    try {
      await strategyApi.closeAllPositions();
      setShowCloseConfirm(false);
      await loadRiskStatus();
    } finally {
      setClosingAll(false);
    }
  };

  // Sync local form state when config loads
  useEffect(() => {
    if (config) {
      setForm({
        enabled: config.enabled,
        min_carry_apy: config.min_carry_apy,
        max_leverage: config.max_leverage,
        max_position_pct: config.max_position_pct,
        max_concurrent_positions: config.max_concurrent_positions,
        stop_loss_pct: config.stop_loss_pct,
        take_profit_pct: config.take_profit_pct ?? 0,
        min_exit_carry_apy: config.min_exit_carry_apy,
        auto_reopen: config.auto_reopen,
        cooldown_minutes: config.cooldown_minutes,
        max_funding_volatility: config.max_funding_volatility,
      });
      setDirty(false);
    }
  }, [config]);

  const update = (key: string, value: any) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const handleSave = async () => {
    const updates: Record<string, any> = { ...form };
    // Convert take_profit 0 → null (disabled)
    if (updates.take_profit_pct === 0) {
      updates.take_profit_pct = null;
    }
    await save(updates);
    setDirty(false);
  };

  const handleToggleEnabled = async () => {
    if (config?.enabled) {
      await pause();
    } else {
      await resume();
    }
  };

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h2 className="text-lg font-medium mb-4">Autonomous Strategy</h2>
        <div className="flex justify-center py-8">
          <LoadingSpinner size="md" />
        </div>
      </div>
    );
  }

  if (!config) return null;

  return (
    <div className="space-y-6">
      {/* Master Toggle */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-medium">Autonomous Strategy</h2>
            <p className="text-sm text-gray-400 mt-1">
              {config.enabled
                ? 'Bot is actively trading based on your configuration.'
                : 'Enable to let the bot trade automatically.'}
            </p>
            {config.is_default && (
              <p className="text-xs text-yellow-500 mt-1">
                Using default settings. Adjust below and save to customize.
              </p>
            )}
          </div>
          <button
            onClick={handleToggleEnabled}
            disabled={saving}
            className={`relative inline-flex h-7 w-14 items-center rounded-full transition-colors ${
              config.enabled ? 'bg-green-600' : 'bg-gray-600'
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                config.enabled ? 'translate-x-8' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
        {error && (
          <p className="text-sm text-red-400 mt-2">{error}</p>
        )}
      </div>

      {/* Bot Status & Risk (7.4.4) */}
      {riskStatus && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-md font-medium">Bot Status</h3>
            <span className={`px-3 py-1 rounded-full text-xs font-medium ${
              riskStatus.bot_status === 'active'
                ? 'bg-green-900/50 text-green-400 border border-green-700'
                : riskStatus.bot_status === 'paused'
                ? 'bg-yellow-900/50 text-yellow-400 border border-yellow-700'
                : 'bg-gray-700 text-gray-400 border border-gray-600'
            }`}>
              {riskStatus.bot_status === 'active' ? 'Active' :
               riskStatus.bot_status === 'paused' ? 'Paused' : 'Inactive'}
            </span>
          </div>

          {riskStatus.paused_reason && (
            <div className="mb-4 p-3 bg-yellow-900/30 border border-yellow-700/50 rounded-lg">
              <p className="text-sm text-yellow-400">
                Paused: {riskStatus.paused_reason}
              </p>
              <p className="text-xs text-yellow-500 mt-1">
                Review the reason above and resume when ready.
              </p>
            </div>
          )}

          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-gray-400">Drawdown</p>
              <p className={`font-medium ${riskStatus.drawdown_pct > 15 ? 'text-red-400' : 'text-white'}`}>
                {riskStatus.drawdown_pct.toFixed(1)}%
              </p>
              <p className="text-xs text-gray-500">peak ${riskStatus.peak_balance_usd.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-gray-400">Daily Trades</p>
              <p className="font-medium">{riskStatus.daily_trades} / {riskStatus.daily_trade_limit}</p>
            </div>
            <div>
              <p className="text-gray-400">Failures</p>
              <p className={`font-medium ${riskStatus.consecutive_failures >= 2 ? 'text-red-400' : 'text-white'}`}>
                {riskStatus.consecutive_failures}
              </p>
            </div>
          </div>

          {/* Emergency Close All (7.4.2) */}
          <div className="mt-4 pt-4 border-t border-gray-700">
            {!showCloseConfirm ? (
              <button
                onClick={() => setShowCloseConfirm(true)}
                className="px-4 py-2 bg-red-900/50 hover:bg-red-800/50 border border-red-700 text-red-400 rounded-lg text-sm font-medium transition-colors"
              >
                Emergency Close All Positions
              </button>
            ) : (
              <div className="p-3 bg-red-900/30 border border-red-700/50 rounded-lg">
                <p className="text-sm text-red-400 mb-3">
                  This will close ALL open positions at market price and pause your strategy.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handleCloseAll}
                    disabled={closingAll}
                    className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                  >
                    {closingAll && <LoadingSpinner size="sm" />}
                    {closingAll ? 'Closing...' : 'Confirm Close All'}
                  </button>
                  <button
                    onClick={() => setShowCloseConfirm(false)}
                    className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm font-medium transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Entry Thresholds */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h3 className="text-md font-medium mb-4">Entry Thresholds</h3>
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <LabelWithTooltip
              label={`Min Carry APY (${form.min_carry_apy?.toFixed(1)}%)`}
              tooltip={TOOLTIPS.minCarryApy}
            />
            <input
              type="range"
              min="0"
              max="50"
              step="0.5"
              value={form.min_carry_apy ?? 15}
              onChange={(e) => update('min_carry_apy', parseFloat(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0%</span>
              <span>50%</span>
            </div>
          </div>

          <div>
            <LabelWithTooltip
              label={`Max Funding Volatility (${(form.max_funding_volatility * 100)?.toFixed(0)}%)`}
              tooltip={TOOLTIPS.maxFundingVolatility}
            />
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={form.max_funding_volatility ?? 0.5}
              onChange={(e) => update('max_funding_volatility', parseFloat(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0% (any)</span>
              <span>100% (strict)</span>
            </div>
          </div>
        </div>
      </div>

      {/* Position Sizing */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h3 className="text-md font-medium mb-4">Position Sizing</h3>
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <LabelWithTooltip
              label={`Max Leverage (${form.max_leverage?.toFixed(1)}x)`}
              tooltip={TOOLTIPS.maxLeverage}
            />
            <input
              type="range"
              min="1.1"
              max="5"
              step="0.1"
              value={form.max_leverage ?? 3}
              onChange={(e) => update('max_leverage', parseFloat(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>1.1x</span>
              <span>5x (max)</span>
            </div>
          </div>

          <div>
            <LabelWithTooltip
              label={`Max Position Size (${(form.max_position_pct * 100)?.toFixed(0)}% of balance)`}
              tooltip={TOOLTIPS.maxPositionPct}
            />
            <input
              type="range"
              min="0.05"
              max="1"
              step="0.05"
              value={form.max_position_pct ?? 0.25}
              onChange={(e) => update('max_position_pct', parseFloat(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>5%</span>
              <span>100%</span>
            </div>
          </div>

          <div>
            <LabelWithTooltip
              label="Max Concurrent Positions"
              tooltip={TOOLTIPS.maxConcurrentPositions}
            />
            <input
              type="number"
              value={form.max_concurrent_positions ?? 2}
              onChange={(e) => update('max_concurrent_positions', parseInt(e.target.value) || 1)}
              className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg"
              min="1"
              max="3"
            />
          </div>
        </div>
      </div>

      {/* Exit Thresholds */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h3 className="text-md font-medium mb-4">Exit Thresholds</h3>
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <LabelWithTooltip
              label={`Stop Loss (${form.stop_loss_pct?.toFixed(0)}%)`}
              tooltip={TOOLTIPS.stopLossPct}
            />
            <input
              type="range"
              min="1"
              max="50"
              step="1"
              value={form.stop_loss_pct ?? 10}
              onChange={(e) => update('stop_loss_pct', parseInt(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>1%</span>
              <span>50%</span>
            </div>
          </div>

          <div>
            <LabelWithTooltip
              label={`Take Profit (${form.take_profit_pct === 0 ? 'Off' : form.take_profit_pct?.toFixed(0) + '%'})`}
              tooltip={TOOLTIPS.takeProfitPct}
            />
            <input
              type="range"
              min="0"
              max="200"
              step="5"
              value={form.take_profit_pct ?? 0}
              onChange={(e) => update('take_profit_pct', parseInt(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>Off</span>
              <span>200%</span>
            </div>
          </div>

          <div>
            <LabelWithTooltip
              label={`Min Exit Carry APY (${form.min_exit_carry_apy?.toFixed(1)}%)`}
              tooltip={TOOLTIPS.minExitCarryApy}
            />
            <input
              type="range"
              min="0"
              max="30"
              step="0.5"
              value={form.min_exit_carry_apy ?? 5}
              onChange={(e) => update('min_exit_carry_apy', parseFloat(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0%</span>
              <span>30%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Reopen Settings */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h3 className="text-md font-medium mb-4">Auto-Reopen</h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">Auto Reopen</span>
                <LabelWithTooltip label="" tooltip={TOOLTIPS.autoReopen} />
              </div>
              <p className="text-sm text-gray-400">Reopen position after close when conditions are met</p>
            </div>
            <button
              onClick={() => update('auto_reopen', !form.auto_reopen)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                form.auto_reopen ? 'bg-blue-600' : 'bg-gray-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  form.auto_reopen ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          {form.auto_reopen && (
            <div>
              <LabelWithTooltip
                label={`Cooldown (${form.cooldown_minutes} min)`}
                tooltip={TOOLTIPS.cooldownMinutes}
              />
              <input
                type="range"
                min="5"
                max="120"
                step="5"
                value={form.cooldown_minutes ?? 30}
                onChange={(e) => update('cooldown_minutes', parseInt(e.target.value))}
                className="leverage-slider w-full"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>5 min</span>
                <span>120 min</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Save Button */}
      {dirty && (
        <div className="flex justify-end gap-3">
          <button
            onClick={() => {
              // Reset to config values
              if (config) {
                setForm({
                  enabled: config.enabled,
                  min_carry_apy: config.min_carry_apy,
                  max_leverage: config.max_leverage,
                  max_position_pct: config.max_position_pct,
                  max_concurrent_positions: config.max_concurrent_positions,
                  stop_loss_pct: config.stop_loss_pct,
                  take_profit_pct: config.take_profit_pct ?? 0,
                  min_exit_carry_apy: config.min_exit_carry_apy,
                  auto_reopen: config.auto_reopen,
                  cooldown_minutes: config.cooldown_minutes,
                  max_funding_volatility: config.max_funding_volatility,
                });
                setDirty(false);
              }
            }}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm font-medium transition-colors"
          >
            Discard
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
          >
            {saving && <LoadingSpinner size="sm" />}
            {saving ? 'Saving...' : 'Save Strategy'}
          </button>
        </div>
      )}
    </div>
  );
}
