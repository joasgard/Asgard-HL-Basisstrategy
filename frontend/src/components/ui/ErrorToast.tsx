import { useState } from 'react';
import { X, HelpCircle, ChevronDown, ChevronUp } from 'lucide-react';

interface ErrorToastProps {
  title: string;
  message: string;
  code: string;
  docsUrl?: string;
  onClose?: () => void;
}

/**
 * ErrorToast - A user-friendly error display component.
 * 
 * Shows:
 * - Human-readable title with error code
 * - Expandable description
 * - Link to documentation for more info
 */
export function ErrorToast({ title, message, code, docsUrl, onClose }: ErrorToastProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  return (
    <div className="bg-red-900/90 border border-red-700 rounded-lg shadow-lg overflow-hidden min-w-[320px] max-w-md">
      {/* Header */}
      <div className="flex items-start gap-3 p-4">
        <div className="flex-1 min-w-0">
          <h4 className="text-white font-medium text-sm leading-tight">
            {title}
          </h4>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-red-300 hover:text-white transition-colors p-1 -mr-1 -mt-1"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        )}
      </div>
      
      {/* Expandable details */}
      <div className="px-4 pb-2">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-1 text-red-300 text-xs hover:text-white transition-colors"
        >
          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {isExpanded ? 'Hide details' : 'Show details'}
        </button>
        
        {isExpanded && (
          <div className="mt-2 text-red-200 text-sm leading-relaxed">
            {message}
          </div>
        )}
      </div>
      
      {/* Footer with docs link */}
      <div className="flex items-center justify-between px-4 py-2 bg-red-950/50 border-t border-red-800">
        <span className="text-red-400 text-xs font-mono">
          Error: {code}
        </span>
        {docsUrl && (
          <a
            href={docsUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-red-300 text-xs hover:text-white transition-colors"
          >
            <HelpCircle size={12} />
            Learn more
          </a>
        )}
      </div>
    </div>
  );
}

/**
 * ErrorBanner - A larger banner for page-level errors.
 */
export function ErrorBanner({ title, message, code, docsUrl }: Omit<ErrorToastProps, 'onClose'>) {
  return (
    <div className="bg-red-900/20 border border-red-700/50 rounded-lg p-6">
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 rounded-full bg-red-900/50 flex items-center justify-center flex-shrink-0">
          <span className="text-red-400 text-lg">!</span>
        </div>
        <div className="flex-1">
          <h3 className="text-white font-medium mb-1">
            {title}
          </h3>
          <p className="text-red-200/80 text-sm leading-relaxed mb-3">
            {message}
          </p>
          <div className="flex items-center gap-4">
            <span className="text-red-400 text-xs font-mono bg-red-950/50 px-2 py-1 rounded">
              {code}
            </span>
            {docsUrl && (
              <a
                href={docsUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-red-300 text-sm hover:text-white transition-colors underline underline-offset-2"
              >
                View documentation →
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
