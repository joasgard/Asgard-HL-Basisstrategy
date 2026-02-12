import { useState, useEffect } from 'react';
import { usePrivy } from '@privy-io/react-auth';
import { useUIStore } from '../../stores';
import { apiClient } from '../../api/client';

export function OpenPositionButton() {
  const [isLoading, setIsLoading] = useState(false);
  const [isFunded, setIsFunded] = useState<boolean | null>(null);
  const { authenticated, login } = usePrivy();
  const { openModal } = useUIStore();

  // Check balance when authenticated
  useEffect(() => {
    if (!authenticated) {
      setIsFunded(null);
      return;
    }

    let cancelled = false;
    const checkBalance = async () => {
      try {
        const { data } = await apiClient.get('/balances/check');
        if (!cancelled) {
          setIsFunded(data.can_trade === true);
        }
      } catch {
        if (!cancelled) {
          setIsFunded(null); // Unknown state — don't block
        }
      }
    };

    checkBalance();
    return () => { cancelled = true; };
  }, [authenticated]);

  const handleClick = async () => {
    // If not authenticated, prompt to connect
    if (!authenticated) {
      login();
      return;
    }

    if (isFunded === false) {
      openModal('deposit');
      return;
    }

    setIsLoading(true);
    openModal('openPosition');
    setIsLoading(false);
  };

  const getLabel = () => {
    if (!authenticated) return 'Connect to Trade';
    if (isFunded === false) return 'Deposit Required';
    return 'Deploy';
  };

  return (
    <div className="flex-1 flex items-center justify-center">
      <button
        onClick={handleClick}
        disabled={isLoading}
        className="w-full h-full min-h-[80px] py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-xl font-bold text-lg transition-colors flex flex-col items-center justify-center gap-2"
      >
        {isLoading ? (
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
        ) : (
          <>
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span>{getLabel()}</span>
          </>
        )}
      </button>
    </div>
  );
}
