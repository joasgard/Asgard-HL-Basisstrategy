import { useCallback, useEffect, useRef } from 'react';
import { usePrivy } from '@privy-io/react-auth';
import { usePositionsStore, useUIStore } from '../stores';
import { positionsApi } from '../api/positions';
import { formatErrorForDisplay, type ApiError } from '../api/client';

// Stable selector hooks - each selector returns a stable reference
const useSetPositions = () => usePositionsStore((state) => state.setPositions);
const useSetLoading = () => usePositionsStore((state) => state.setLoading);
const useSetError = () => usePositionsStore((state) => state.setError);
const useUpdatePosition = () => usePositionsStore((state) => state.updatePosition);
const useSelectPosition = () => usePositionsStore((state) => state.selectPosition);

export function usePositions() {
  const { authenticated } = usePrivy();
  const { addToast, addErrorToast } = useUIStore();

  // Get store actions - these are stable callbacks from the store
  const setPositions = useSetPositions();
  const setLoading = useSetLoading();
  const setError = useSetError();
  const updatePosition = useUpdatePosition();
  const selectPosition = useSelectPosition();

  // Get store state - use the hook directly in component that needs it
  // Don't subscribe to state here to avoid re-render loops

  // Use ref to prevent duplicate toast spam
  const hasShownErrorRef = useRef(false);

  // Track active polling timeouts for cleanup
  const pollingTimeoutsRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  // Cleanup polling timeouts on unmount
  useEffect(() => {
    return () => {
      pollingTimeoutsRef.current.forEach(clearTimeout);
      pollingTimeoutsRef.current.clear();
    };
  }, []);

  const fetchPositions = useCallback(async () => {
    // Skip if not authenticated
    if (!authenticated) {
      setLoading(false);
      setPositions([]);
      return;
    }

    setLoading(true);
    setError(null);
    
    try {
      const positions = await positionsApi.list();
      setPositions(positions);
      hasShownErrorRef.current = false; // Reset error flag on success
    } catch (error) {
      const apiError = error as ApiError;
      
      // Don't show toast for 401 errors - user is just not logged in
      if (apiError.httpStatus === 401) {
        setPositions([]);
      } else {
        const formatted = formatErrorForDisplay(error);
        setError(formatted.message);
        
        // Only show toast once per error session
        if (!hasShownErrorRef.current) {
          hasShownErrorRef.current = true;
          addErrorToast({
            title: formatted.title,
            message: formatted.message,
            code: formatted.code,
            docsUrl: formatted.docsUrl,
          });
        }
      }
    } finally {
      setLoading(false);
    }
  }, [authenticated, setPositions, setLoading, setError, addErrorToast]);

  const openPosition = useCallback(async (asset: string, leverage: number, sizeUsd: number) => {
    if (!authenticated) {
      addErrorToast({
        title: 'Wallet Not Connected',
        message: 'Please connect your wallet to open positions.',
        code: 'WAL-0004',
      });
      throw new Error('Not authenticated');
    }

    setLoading(true);
    
    try {
      const result = await positionsApi.open({ asset, leverage, size_usd: sizeUsd });
      addToast(`Position opening initiated (Job: ${result.job_id})`, 'success');
      
      // Poll for job completion
      const checkStatus = async () => {
        try {
          const status = await positionsApi.getJobStatus(result.job_id);
          if (status.status === 'completed' && status.position_id) {
            // Refresh positions to get the new one
            await fetchPositions();
            addToast('Position opened successfully', 'success');
          } else if (status.status === 'failed') {
            // Job failed - use error code if available
            if (status.error_code) {
              const formatted = formatErrorForDisplay({ 
                error_code: status.error_code,
                message: status.error || 'Failed to open position'
              });
              addErrorToast({
                title: formatted.title,
                message: formatted.message,
                code: formatted.code,
                docsUrl: formatted.docsUrl,
              });
            } else {
              addToast(status.error || 'Failed to open position', 'error');
            }
          } else {
            // Still pending, check again
            const tid = setTimeout(checkStatus, 2000);
            pollingTimeoutsRef.current.add(tid);
          }
        } catch (e) {
          console.error('Failed to check job status:', e);
        }
      };
      
      const tid = setTimeout(checkStatus, 2000);
      pollingTimeoutsRef.current.add(tid);
      return result;
    } catch (error) {
      const formatted = formatErrorForDisplay(error);
      setError(formatted.message);
      addErrorToast({
        title: formatted.title,
        message: formatted.message,
        code: formatted.code,
        docsUrl: formatted.docsUrl,
      });
      throw error;
    } finally {
      setLoading(false);
    }
  }, [authenticated, setLoading, setError, addToast, addErrorToast, fetchPositions]);

  const closePosition = useCallback(async (positionId: string) => {
    if (!authenticated) {
      addErrorToast({
        title: 'Wallet Not Connected',
        message: 'Please connect your wallet to close positions.',
        code: 'WAL-0004',
      });
      throw new Error('Not authenticated');
    }

    setLoading(true);
    
    try {
      const result = await positionsApi.close(positionId);
      addToast(`Position closing initiated (Job: ${result.job_id})`, 'info');
      
      // Poll for job completion
      const checkStatus = async () => {
        try {
          const status = await positionsApi.getJobStatus(result.job_id);
          if (status.status === 'completed') {
            updatePosition(positionId, { status: 'closed' });
            addToast('Position closed successfully', 'success');
          } else if (status.status === 'failed') {
            // Job failed - use error code if available
            if (status.error_code) {
              const formatted = formatErrorForDisplay({ 
                error_code: status.error_code,
                message: status.error || 'Failed to close position'
              });
              addErrorToast({
                title: formatted.title,
                message: formatted.message,
                code: formatted.code,
                docsUrl: formatted.docsUrl,
              });
            } else {
              addToast(status.error || 'Failed to close position', 'error');
            }
          } else {
            // Still pending, check again
            const tid = setTimeout(checkStatus, 2000);
            pollingTimeoutsRef.current.add(tid);
          }
        } catch (e) {
          console.error('Failed to check job status:', e);
        }
      };
      
      const tid = setTimeout(checkStatus, 2000);
      pollingTimeoutsRef.current.add(tid);
    } catch (error) {
      const formatted = formatErrorForDisplay(error);
      setError(formatted.message);
      addErrorToast({
        title: formatted.title,
        message: formatted.message,
        code: formatted.code,
        docsUrl: formatted.docsUrl,
      });
      throw error;
    } finally {
      setLoading(false);
    }
  }, [authenticated, setLoading, setError, addToast, addErrorToast, updatePosition]);

  const refreshPosition = useCallback(async (positionId: string) => {
    try {
      const position = await positionsApi.get(positionId);
      updatePosition(positionId, position);
      return position;
    } catch (error) {
      const formatted = formatErrorForDisplay(error);
      addErrorToast({
        title: formatted.title,
        message: formatted.message,
        code: formatted.code,
        docsUrl: formatted.docsUrl,
      });
      throw error;
    }
  }, [addErrorToast, updatePosition]);

  return {
    // Actions only - let components subscribe to state directly
    fetchPositions,
    openPosition,
    closePosition,
    refreshPosition,
    selectPosition,
  };
}
