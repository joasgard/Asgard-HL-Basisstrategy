import { useCallback } from 'react';
import { useSettingsStore, PresetType, useUIStore } from '../stores';

// Stable selector hooks for actions
const useUpdateSettings = () => useSettingsStore((state) => state.updateSettings);
const useApplyPreset = () => useSettingsStore((state) => state.applyPreset);
const useSaveSettings = () => useSettingsStore((state) => state.saveSettings);
const useLoadSettings = () => useSettingsStore((state) => state.loadSettings);
const useResetSettings = () => useSettingsStore((state) => state.resetSettings);

export function useSettings() {
  const { addToast } = useUIStore();
  
  // Get stable action references
  const updateSettingsStore = useUpdateSettings();
  const applyPresetStore = useApplyPreset();
  const saveSettingsStore = useSaveSettings();
  const loadSettingsStore = useLoadSettings();
  const resetSettingsStore = useResetSettings();

  const updateSettings = useCallback((settings: Parameters<typeof updateSettingsStore>[0]) => {
    updateSettingsStore(settings);
  }, [updateSettingsStore]);

  const applyPreset = useCallback((preset: PresetType) => {
    applyPresetStore(preset);
    addToast(`${preset.charAt(0).toUpperCase() + preset.slice(1)} preset applied`, 'info');
  }, [applyPresetStore, addToast]);

  const saveSettings = useCallback(async () => {
    try {
      await saveSettingsStore();
      addToast('Settings saved successfully', 'success');
    } catch (error) {
      addToast('Failed to save settings', 'error');
      throw error;
    }
  }, [saveSettingsStore, addToast]);

  const loadSettings = useCallback(async () => {
    try {
      await loadSettingsStore();
    } catch (error) {
      addToast('Failed to load settings', 'error');
    }
  }, [loadSettingsStore, addToast]);

  const resetSettings = useCallback(() => {
    resetSettingsStore();
    addToast('Settings reset to defaults', 'info');
  }, [resetSettingsStore, addToast]);

  return {
    // Actions only - components should subscribe to state directly
    updateSettings,
    applyPreset,
    saveSettings,
    loadSettings,
    resetSettings,
  };
}
