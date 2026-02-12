import { useEffect } from 'react';
import { useSettings } from '../../hooks';
import { useSettingsStore } from '../../stores';
import type { PresetType } from '../../stores';
import { LoadingSpinner, LabelWithTooltip } from '../ui';

const PRESET_CONFIG: Record<PresetType, { name: string; description: string; tooltip: string }> = {
  conservative: {
    name: 'Conservative',
    description: 'Lower risk, smaller positions',
    tooltip: 'Uses 2x leverage with strict stop losses, low volatility tolerance, and auto-exit enabled for maximum capital preservation',
  },
  balanced: {
    name: 'Balanced',
    description: 'Moderate risk and reward',
    tooltip: 'Uses 3x leverage with moderate risk controls - the default for most traders',
  },
  aggressive: {
    name: 'Aggressive',
    description: 'Higher risk, larger positions',
    tooltip: 'Uses 4x leverage with disabled circuit breakers, higher volatility tolerance for maximum yield',
  },
};

const SETTING_TOOLTIPS = {
  defaultLeverage: 'Multiplies your position size. Higher leverage = higher yield but higher liquidation risk. Range: 1.1x - 4x',
  maxPositionSize: 'Maximum USD value for any single position. Prevents accidental oversized trades',
  minPositionSize: 'Minimum USD value for any single position. Must be at least $100 due to protocol constraints',
  maxPositionsPerAsset: 'Maximum number of concurrent positions allowed per asset (1-5)',
  minOpportunityApy: 'Minimum carry APY required to open a position. Filter out low-yield opportunities',
  maxFundingVolatility: 'Skip opportunities if funding rate volatility exceeds this threshold (0-100%)',
  priceDeviationThreshold: 'Maximum price difference allowed between Asgard and Hyperliquid before pausing (0.1-5%)',
  deltaDriftThreshold: 'Trigger rebalance when position delta drifts beyond this threshold (0.1-5%)',
  stopLossPercent: 'Automatically close position if loss exceeds this percentage. Set to 0 to disable',
  takeProfitPercent: 'Automatically close position when profit reaches this percentage. Set to 0 to disable',
  autoExit: 'Automatically close positions when stop loss is hit or funding rates turn unfavorable',
  circuitBreakers: 'Pause new position openings when funding rates spike or market volatility is high',
};

export function Settings() {
  const {
    updateSettings,
    applyPreset,
    saveSettings,
    loadSettings,
    resetSettings,
  } = useSettings();

  // Subscribe to store state directly
  const defaultLeverage = useSettingsStore((state) => state.defaultLeverage);
  const minPositionSize = useSettingsStore((state) => state.minPositionSize);
  const maxPositionSize = useSettingsStore((state) => state.maxPositionSize);
  const maxPositionsPerAsset = useSettingsStore((state) => state.maxPositionsPerAsset);
  const minOpportunityApy = useSettingsStore((state) => state.minOpportunityApy);
  const maxFundingVolatility = useSettingsStore((state) => state.maxFundingVolatility);
  const priceDeviationThreshold = useSettingsStore((state) => state.priceDeviationThreshold);
  const deltaDriftThreshold = useSettingsStore((state) => state.deltaDriftThreshold);
  const stopLossPercent = useSettingsStore((state) => state.stopLossPercent);
  const takeProfitPercent = useSettingsStore((state) => state.takeProfitPercent);
  const enableAutoExit = useSettingsStore((state) => state.enableAutoExit);
  const enableCircuitBreakers = useSettingsStore((state) => state.enableCircuitBreakers);
  const selectedPreset = useSettingsStore((state) => state.selectedPreset);
  const isLoading = useSettingsStore((state) => state.isLoading);
  const isDirty = useSettingsStore((state) => state.isDirty);

  const settings = {
    defaultLeverage,
    minPositionSize,
    maxPositionSize,
    maxPositionsPerAsset,
    minOpportunityApy,
    maxFundingVolatility,
    priceDeviationThreshold,
    deltaDriftThreshold,
    stopLossPercent,
    takeProfitPercent,
    enableAutoExit,
    enableCircuitBreakers,
  };

  // Load settings on mount
  useEffect(() => {
    loadSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handlePresetSelect = (presetKey: PresetType) => {
    applyPreset(presetKey);
  };

  const handleSettingChange = (key: keyof typeof settings, value: number | boolean) => {
    updateSettings({ [key]: value });
  };

  const handleSave = async () => {
    await saveSettings();
  };

  const handleReset = () => {
    if (confirm('Are you sure you want to reset all settings to defaults?')) {
      resetSettings();
    }
  };

  if (isLoading && !settings) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Settings</h1>
        {isDirty && (
          <span className="text-sm text-yellow-400">Unsaved changes</span>
        )}
      </div>

      {/* Presets */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h2 className="text-lg font-medium mb-4">Strategy Presets</h2>
        <div className="grid md:grid-cols-3 gap-4">
          {(Object.keys(PRESET_CONFIG) as PresetType[]).map((key) => (
            <button
              key={key}
              onClick={() => handlePresetSelect(key)}
              className={`p-4 rounded-lg border text-left transition-colors ${
                selectedPreset === key
                  ? 'border-blue-500 bg-blue-900/20'
                  : 'border-gray-600 hover:border-gray-500'
              }`}
              title={PRESET_CONFIG[key].tooltip}
            >
              <h3 className="font-medium text-white">{PRESET_CONFIG[key].name}</h3>
              <p className="text-sm text-gray-400 mt-1">{PRESET_CONFIG[key].description}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Position Settings */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h2 className="text-lg font-medium mb-4">Position Settings</h2>
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <LabelWithTooltip 
              label={`Default Leverage (${settings.defaultLeverage}x)`}
              tooltip={SETTING_TOOLTIPS.defaultLeverage}
            />
            <input
              type="range"
              min="1.1"
              max="4"
              step="0.1"
              value={settings.defaultLeverage}
              onChange={(e) => handleSettingChange('defaultLeverage', parseFloat(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>1.1x</span>
              <span>4x</span>
            </div>
          </div>

          <div>
            <LabelWithTooltip 
              label="Max Positions Per Asset"
              tooltip={SETTING_TOOLTIPS.maxPositionsPerAsset}
            />
            <input
              type="number"
              value={settings.maxPositionsPerAsset}
              onChange={(e) => handleSettingChange('maxPositionsPerAsset', parseInt(e.target.value))}
              className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg"
              min="1"
              max="5"
              step="1"
            />
          </div>

          <div>
            <LabelWithTooltip 
              label="Min Position Size (USD)"
              tooltip={SETTING_TOOLTIPS.minPositionSize}
            />
            <input
              type="number"
              value={settings.minPositionSize}
              onChange={(e) => handleSettingChange('minPositionSize', parseInt(e.target.value))}
              className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg"
              min="100"
              step="100"
            />
          </div>

          <div>
            <LabelWithTooltip 
              label="Max Position Size (USD)"
              tooltip={SETTING_TOOLTIPS.maxPositionSize}
            />
            <input
              type="number"
              value={settings.maxPositionSize}
              onChange={(e) => handleSettingChange('maxPositionSize', parseInt(e.target.value))}
              className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg"
              min="100"
              step="100"
            />
          </div>
        </div>
      </div>

      {/* Opportunity Filters */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h2 className="text-lg font-medium mb-4">Opportunity Filters</h2>
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <LabelWithTooltip 
              label={`Min Opportunity APY (${settings.minOpportunityApy}%)`}
              tooltip={SETTING_TOOLTIPS.minOpportunityApy}
            />
            <input
              type="range"
              min="0"
              max="10"
              step="0.5"
              value={settings.minOpportunityApy}
              onChange={(e) => handleSettingChange('minOpportunityApy', parseFloat(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0%</span>
              <span>10%</span>
            </div>
          </div>

          <div>
            <LabelWithTooltip 
              label={`Max Funding Volatility (${settings.maxFundingVolatility}%)`}
              tooltip={SETTING_TOOLTIPS.maxFundingVolatility}
            />
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={settings.maxFundingVolatility}
              onChange={(e) => handleSettingChange('maxFundingVolatility', parseInt(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0%</span>
              <span>100%</span>
            </div>
          </div>

          <div>
            <LabelWithTooltip 
              label={`Price Deviation Threshold (${settings.priceDeviationThreshold}%)`}
              tooltip={SETTING_TOOLTIPS.priceDeviationThreshold}
            />
            <input
              type="range"
              min="0.1"
              max="5"
              step="0.1"
              value={settings.priceDeviationThreshold}
              onChange={(e) => handleSettingChange('priceDeviationThreshold', parseFloat(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0.1%</span>
              <span>5%</span>
            </div>
          </div>

          <div>
            <LabelWithTooltip 
              label={`Delta Drift Threshold (${settings.deltaDriftThreshold}%)`}
              tooltip={SETTING_TOOLTIPS.deltaDriftThreshold}
            />
            <input
              type="range"
              min="0.1"
              max="5"
              step="0.1"
              value={settings.deltaDriftThreshold}
              onChange={(e) => handleSettingChange('deltaDriftThreshold', parseFloat(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0.1%</span>
              <span>5%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Exit Settings */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h2 className="text-lg font-medium mb-4">Exit Settings</h2>
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <LabelWithTooltip 
              label={`Stop Loss (${settings.stopLossPercent}%)`}
              tooltip={SETTING_TOOLTIPS.stopLossPercent}
            />
            <input
              type="range"
              min="0"
              max="50"
              step="1"
              value={settings.stopLossPercent}
              onChange={(e) => handleSettingChange('stopLossPercent', parseInt(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0% (Off)</span>
              <span>50%</span>
            </div>
          </div>

          <div>
            <LabelWithTooltip 
              label={`Take Profit (${settings.takeProfitPercent}%)`}
              tooltip={SETTING_TOOLTIPS.takeProfitPercent}
            />
            <input
              type="range"
              min="0"
              max="200"
              step="10"
              value={settings.takeProfitPercent}
              onChange={(e) => handleSettingChange('takeProfitPercent', parseInt(e.target.value))}
              className="leverage-slider w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0% (Off)</span>
              <span>200%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Risk Management */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h2 className="text-lg font-medium mb-4">Risk Management</h2>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className="font-medium">Auto Exit</h3>
                <LabelWithTooltip label="" tooltip={SETTING_TOOLTIPS.autoExit} />
              </div>
              <p className="text-sm text-gray-400">Automatically close positions when risk thresholds are met</p>
            </div>
            <button
              onClick={() => handleSettingChange('enableAutoExit', !settings.enableAutoExit)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                settings.enableAutoExit ? 'bg-blue-600' : 'bg-gray-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  settings.enableAutoExit ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className="font-medium">Circuit Breakers</h3>
                <LabelWithTooltip label="" tooltip={SETTING_TOOLTIPS.circuitBreakers} />
              </div>
              <p className="text-sm text-gray-400">Pause trading when market conditions are unfavorable</p>
            </div>
            <button
              onClick={() => handleSettingChange('enableCircuitBreakers', !settings.enableCircuitBreakers)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                settings.enableCircuitBreakers ? 'bg-blue-600' : 'bg-gray-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  settings.enableCircuitBreakers ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex justify-between">
        <button
          onClick={handleReset}
          className="px-6 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg font-medium transition-colors"
        >
          Reset to Defaults
        </button>
        <div className="flex gap-3">
          <button
            onClick={handleSave}
            disabled={isLoading || !isDirty}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            {isLoading && <LoadingSpinner size="sm" />}
            {isLoading ? 'Saving...' : isDirty ? 'Save Changes' : 'Saved'}
          </button>
        </div>
      </div>
    </div>
  );
}
