import { useUIStore } from '../../stores';
import { LoadingSpinner } from './LoadingSpinner';

export function GlobalLoading() {
  const { globalLoading, loadingMessage } = useUIStore();

  if (!globalLoading) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center">
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 text-center">
        <LoadingSpinner size="lg" className="mb-4" />
        {loadingMessage && (
          <p className="text-gray-300">{loadingMessage}</p>
        )}
      </div>
    </div>
  );
}
