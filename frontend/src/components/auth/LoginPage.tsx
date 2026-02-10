import { usePrivy } from '@privy-io/react-auth';

export function LoginPage() {
  const { login } = usePrivy();

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
      <div className="bg-gray-800 rounded-xl p-8 max-w-md w-full border border-gray-700">
        {/* Logo */}
        <div className="text-center mb-6">
          <img 
            src="/asgard.png" 
            alt="Asgard" 
            className="w-20 h-20 mx-auto mb-4 rounded-full"
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
          />
          <h1 className="text-2xl font-bold text-white">Delta Neutral Bot</h1>
          <p className="text-gray-400 mt-1">Connect your wallet to start</p>
        </div>

        {/* Login Button */}
        <button
          onClick={login}
          className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          Continue with Email
        </button>

        {/* Protected by Privy */}
        <div className="mt-6 text-center text-xs text-gray-500">
          Protected by 🔒 <a href="https://privy.io" target="_blank" rel="noopener noreferrer" className="hover:text-gray-400">Privy</a>
        </div>
      </div>
    </div>
  );
}
