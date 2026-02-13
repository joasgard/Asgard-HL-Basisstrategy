import { useState, useEffect, useCallback } from 'react';
import { strategyApi, type StrategyConfig, type StrategyConfigUpdate } from '../api/strategy';

interface UseStrategyConfigReturn {
  config: StrategyConfig | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  reload: () => Promise<void>;
  save: (updates: Omit<StrategyConfigUpdate, 'version'>) => Promise<boolean>;
  pause: () => Promise<boolean>;
  resume: () => Promise<boolean>;
}

export function useStrategyConfig(): UseStrategyConfigReturn {
  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await strategyApi.get();
      setConfig(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load strategy config');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const save = useCallback(
    async (updates: Omit<StrategyConfigUpdate, 'version'>): Promise<boolean> => {
      if (!config) return false;
      try {
        setSaving(true);
        setError(null);
        const result = await strategyApi.update({
          ...updates,
          version: config.version,
        });
        setConfig(result);
        return true;
      } catch (e: any) {
        const detail = e?.response?.data?.detail;
        if (e?.response?.status === 409) {
          setError('Config was modified elsewhere. Reloading...');
          await reload();
        } else {
          setError(detail || 'Failed to save');
        }
        return false;
      } finally {
        setSaving(false);
      }
    },
    [config, reload],
  );

  const pause = useCallback(async (): Promise<boolean> => {
    try {
      setSaving(true);
      await strategyApi.pause();
      await reload();
      return true;
    } catch {
      setError('Failed to pause strategy');
      return false;
    } finally {
      setSaving(false);
    }
  }, [reload]);

  const resume = useCallback(async (): Promise<boolean> => {
    try {
      setSaving(true);
      await strategyApi.resume();
      await reload();
      return true;
    } catch {
      setError('Failed to resume strategy');
      return false;
    } finally {
      setSaving(false);
    }
  }, [reload]);

  return { config, loading, saving, error, reload, save, pause, resume };
}
