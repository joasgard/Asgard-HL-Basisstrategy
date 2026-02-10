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
            onError={(e) => { 
              e.currentTarget.style.display = 'none'; 
            }}
          />
          <h1 className="text-2xl font-bold text-white">Delta Neutral Bot</h1>
          <p className="text-gray-400 mt-1">Connect your wallet to start</p>
        </div>

        {/* Login Button */}
        <button
          onClick={login}
          className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
        >
          <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          <span>Continue with Email</span>
        </button>

        {/* Protected by Privy */}
        <div className="mt-6 text-center text-xs text-gray-500 flex items-center justify-center gap-1">
          <span>Protected by</span>
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" />
          </svg>
          <a href="https://privy.io" target="_blank" rel="noopener noreferrer" className="hover:text-gray-400">
            Privy
          </a>
        </div>
      </div>
    </div>
  );
}
