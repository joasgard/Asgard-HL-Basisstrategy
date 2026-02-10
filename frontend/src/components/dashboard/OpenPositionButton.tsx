import { useState } from 'react';

interface OpenPositionButtonProps {
  leverage: number;
}

export function OpenPositionButton({ leverage }: OpenPositionButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [isFunded] = useState(true); // TODO: Check actual balance

  const handleClick = async () => {
    if (!isFunded) return;
    setIsLoading(true);
    // TODO: Implement position opening
    console.log('Opening position at', leverage, 'x leverage');
    setTimeout(() => setIsLoading(false), 2000);
  };

  return (
    <div className="flex-1 flex items-center justify-center">
      <button
        onClick={handleClick}
        disabled={!isFunded || isLoading}
        className="w-full h-full min-h-[80px] py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-xl font-bold text-lg transition-colors flex flex-col items-center justify-center gap-2"
      >
        {isLoading ? (
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
        ) : (
          <>
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span>{isFunded ? 'Open Position' : 'Deposit Required'}</span>
          </>
        )}
      </button>
    </div>
  );
}
