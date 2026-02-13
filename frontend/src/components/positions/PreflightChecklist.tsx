import { useState, useEffect, useCallback } from 'react';
import { positionsApi, type OpenPositionRequest, type PreflightCheck } from '../../api/positions';

type CheckStatus = 'pending' | 'passed' | 'failed';

interface CheckDisplay {
  key: string;
  label: string;
  status: CheckStatus;
  error: string | null;
  visible: boolean;
}

const INITIAL_CHECKS: CheckDisplay[] = [
  { key: 'wallet_balance', label: 'Wallet balances', status: 'pending', error: null, visible: false },
  { key: 'price_consensus', label: 'Price consensus', status: 'pending', error: null, visible: false },
  { key: 'funding_validation', label: 'Funding rates', status: 'pending', error: null, visible: false },
  { key: 'protocol_capacity', label: 'Protocol capacity', status: 'pending', error: null, visible: false },
  { key: 'fee_market', label: 'Fee market', status: 'pending', error: null, visible: false },
  { key: 'opportunity_simulation', label: 'Position simulation', status: 'pending', error: null, visible: false },
];

interface PreflightChecklistProps {
  request: OpenPositionRequest;
  onAllPassed: () => void;
  onDismiss: () => void;
}

function SpinnerIcon() {
  return (
    <svg
      className="w-5 h-5 text-blue-400 animate-spin"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

export function PreflightChecklist({ request, onAllPassed, onDismiss }: PreflightChecklistProps) {
  const [checks, setChecks] = useState<CheckDisplay[]>(INITIAL_CHECKS);
  const [phase, setPhase] = useState<'checking' | 'passed' | 'failed' | 'opening'>('checking');
  const [failCount, setFailCount] = useState(0);

  const runChecks = useCallback(async () => {
    // Reset to pending
    setChecks(INITIAL_CHECKS.map(c => ({ ...c, visible: false })));
    setPhase('checking');
    setFailCount(0);

    // Stagger initial visibility — show all checks as pending with delay
    INITIAL_CHECKS.forEach((_, i) => {
      setTimeout(() => {
        setChecks(prev => prev.map((c, j) => j === i ? { ...c, visible: true } : c));
      }, i * 100);
    });

    try {
      const result = await positionsApi.preflight(request);

      // Stagger result reveal
      result.checks.forEach((check: PreflightCheck, i: number) => {
        setTimeout(() => {
          setChecks(prev =>
            prev.map(c =>
              c.key === check.key
                ? { ...c, status: check.passed ? 'passed' : 'failed', error: check.error, visible: true }
                : c
            )
          );
        }, i * 200);
      });

      // After all reveals, set final phase
      const revealDone = result.checks.length * 200 + 100;
      setTimeout(() => {
        if (result.passed) {
          setPhase('passed');
        } else {
          const failed = result.checks.filter(c => !c.passed).length;
          setFailCount(failed);
          setPhase('failed');
        }
      }, revealDone);
    } catch {
      // API error — mark all as failed
      setChecks(prev => prev.map(c => ({
        ...c,
        status: 'failed' as const,
        error: 'Connection error',
        visible: true,
      })));
      setFailCount(6);
      setPhase('failed');
    }
  }, [request]);

  // Auto-proceed when all pass
  useEffect(() => {
    if (phase === 'passed') {
      setPhase('opening');
      onAllPassed();
    }
  }, [phase, onAllPassed]);

  // Run on mount
  useEffect(() => {
    runChecks();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="fixed bottom-4 left-4 z-50 w-80 bg-gray-900 border border-gray-700 rounded-lg shadow-xl">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <h3 className="text-sm font-semibold text-white">Preflight Checks</h3>
        <button
          onClick={onDismiss}
          className="text-gray-400 hover:text-white transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Check list */}
      <ul className="px-4 py-3 space-y-2">
        {checks.map(check => (
          <li
            key={check.key}
            className={`transition-all duration-300 ${check.visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-1'}`}
          >
            <div className="flex items-center gap-2">
              {check.status === 'pending' && <SpinnerIcon />}
              {check.status === 'passed' && <CheckIcon />}
              {check.status === 'failed' && <XIcon />}
              <span className={`text-sm ${check.status === 'failed' ? 'text-red-300' : 'text-gray-300'}`}>
                {check.label}
              </span>
            </div>
            {check.status === 'failed' && check.error && (
              <p className="ml-7 text-xs text-red-400 mt-0.5">{check.error}</p>
            )}
          </li>
        ))}
      </ul>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-700">
        {phase === 'checking' && (
          <p className="text-xs text-gray-400">Running checks...</p>
        )}
        {phase === 'opening' && (
          <p className="text-xs text-blue-400">Opening position...</p>
        )}
        {phase === 'failed' && (
          <div className="flex items-center justify-between">
            <p className="text-xs text-red-400">
              {failCount} check{failCount !== 1 ? 's' : ''} failed
            </p>
            <button
              onClick={runChecks}
              className="text-xs text-blue-400 hover:text-blue-300 font-medium transition-colors"
            >
              Retry
            </button>
          </div>
        )}
        {phase === 'passed' && (
          <p className="text-xs text-green-400">All checks passed</p>
        )}
      </div>
    </div>
  );
}
