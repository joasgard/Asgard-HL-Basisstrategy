import { NavLink } from 'react-router-dom';
import { usePrivy } from '@privy-io/react-auth';

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const { user, logout } = usePrivy();

  const navItems = [
    { path: '/', label: 'Dashboard', icon: '📊' },
    { path: '/positions', label: 'Positions', icon: '📈' },
    { path: '/settings', label: 'Settings', icon: '⚙️' },
  ];

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Security Banner */}
      <div className="bg-yellow-900/50 border-b border-yellow-700 px-4 py-2">
        <div className="max-w-7xl mx-auto flex items-center gap-2 text-yellow-200 text-sm">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <span><strong>Security Notice:</strong> Your data is encrypted. Wallets are managed by Privy.</span>
        </div>
      </div>

      {/* Header */}
      <header className="border-b border-gray-700 bg-gray-800/50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold">🤖 Delta Neutral Bot</h1>
          </div>
          
          <div className="flex items-center gap-4">
            {user?.email && (
              <span className="text-sm text-gray-400">{user.email.address}</span>
            )}
            <button
              onClick={logout}
              className="text-sm text-gray-400 hover:text-white transition-colors"
            >
              Disconnect
            </button>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="border-b border-gray-700 bg-gray-800/30">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-6">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `py-4 px-2 flex items-center gap-2 transition-colors ${
                    isActive
                      ? 'tab-active border-b-2 border-blue-500 text-blue-500'
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
    </div>
  );
}
