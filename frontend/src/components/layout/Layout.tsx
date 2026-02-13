import { NavLink } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { usePrivy } from '@privy-io/react-auth';
import { DepositModal } from '../modals/DepositModal';
import { WithdrawModal } from '../modals/WithdrawModal';
import { useAuth } from '../../hooks/useAuth';

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const { authenticated, user, login, logout } = usePrivy();
  const { backendSynced, syncError, retrySync } = useAuth();
  const [isDepositModalOpen, setIsDepositModalOpen] = useState(false);
  const [isWithdrawModalOpen, setIsWithdrawModalOpen] = useState(false);
  const [showSyncError, setShowSyncError] = useState(false);

  // Show sync error if backend sync fails
  useEffect(() => {
    if (syncError && authenticated) {
      setShowSyncError(true);
      const timer = setTimeout(() => setShowSyncError(false), 5000);
      return () => clearTimeout(timer);
    }
  }, [syncError, authenticated]);

  const navItems = [
    { path: '/', label: 'Dashboard', icon: '📊' },
    { path: '/positions', label: 'Positions', icon: '📈' },
    { path: '/settings', label: 'Settings', icon: '⚙️' },
  ];

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="border-b border-gray-700 bg-gray-800/50 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img 
              src="/asgard.png" 
              alt="Asgard" 
              className="w-8 h-8 rounded-full"
            />
            <h1 className="text-xl font-bold">Asgard Basis</h1>
          </div>
          
          <div className="flex items-center gap-4">
            {authenticated ? (
              <>
                {user?.email && (
                  <span className="text-sm text-gray-400">{user.email.address}</span>
                )}
                {/* Backend sync indicator */}
                {!backendSynced && !syncError && (
                  <span className="text-xs text-gray-500" title="Connecting to backend">
                    Connecting...
                  </span>
                )}
                {!backendSynced && syncError && (
                  <button
                    onClick={retrySync}
                    className="text-xs text-yellow-400 hover:text-yellow-300"
                    title="Click to retry"
                  >
                    Sync failed - retry
                  </button>
                )}
                <button
                  onClick={() => setIsDepositModalOpen(true)}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Deposit
                </button>
                <button
                  onClick={() => setIsWithdrawModalOpen(true)}
                  className="px-3 py-2 bg-gray-600 hover:bg-gray-500 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                  </svg>
                  Withdraw
                </button>
                <button
                  onClick={logout}
                  className="text-sm text-gray-400 hover:text-white transition-colors"
                >
                  Disconnect
                </button>
              </>
            ) : (
              <button
                onClick={login}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
                Connect
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Sync error banner — only after login, when backend sync actually fails */}
      {showSyncError && authenticated && (
        <div className="bg-yellow-900/30 border-b border-yellow-700/50 px-6 py-2">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <span className="text-sm text-yellow-400">
              Could not connect to backend. Retrying...
            </span>
            <button
              onClick={retrySync}
              className="text-xs text-yellow-300 hover:text-yellow-200 underline"
            >
              Retry now
            </button>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="border-b border-gray-700 bg-gray-800/30 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-6">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `py-4 px-2 flex items-center gap-2 transition-colors ${
                    isActive
                      ? 'tab-active'
                      : 'text-gray-400 hover:text-white'
                  }`
                }
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto p-6">
        {children}
      </main>

      {/* Deposit Modal */}
      <DepositModal
        isOpen={isDepositModalOpen}
        onClose={() => setIsDepositModalOpen(false)}
      />

      {/* Withdraw Modal */}
      <WithdrawModal
        isOpen={isWithdrawModalOpen}
        onClose={() => setIsWithdrawModalOpen(false)}
      />
    </div>
  );
}
