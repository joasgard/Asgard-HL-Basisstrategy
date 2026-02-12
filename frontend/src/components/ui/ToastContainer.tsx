import { useUIStore, ToastType } from '../../stores';
import { ErrorToast } from './ErrorToast';

const toastStyles: Record<ToastType, string> = {
  success: 'bg-green-600',
  error: 'bg-red-600',
  warning: 'bg-yellow-600',
  info: 'bg-blue-600',
};

const toastIcons: Record<ToastType, string> = {
  success: '✓',
  error: '✕',
  warning: '⚠',
  info: 'ℹ',
};

export function ToastContainer() {
  const { toasts, removeToast } = useUIStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2">
      {toasts.map((toast) => {
        // Use ErrorToast for error toasts that have error codes
        if (toast.type === 'error' && toast.errorCode) {
          return (
            <ErrorToast
              key={toast.id}
              title={toast.message}
              message={toast.errorDescription || ''}
              code={toast.errorCode}
              docsUrl={toast.docsUrl}
              onClose={() => removeToast(toast.id)}
            />
          );
        }

        // Standard toast for all other types
        return (
          <div
            key={toast.id}
            className={`${toastStyles[toast.type]} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 min-w-[300px] animate-slide-in`}
            role="alert"
          >
            <span className="flex-shrink-0 w-6 h-6 bg-white/20 rounded-full flex items-center justify-center text-sm">
              {toastIcons[toast.type]}
            </span>
            <p className="flex-1">{toast.message}</p>
            <button
              onClick={() => removeToast(toast.id)}
              className="flex-shrink-0 text-white/70 hover:text-white"
              aria-label="Close"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        );
      })}
    </div>
  );
}
