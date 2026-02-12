import { usePrivy } from '@privy-io/react-auth';

export function LoginPage() {
  const { login } = usePrivy();

  const handleLogin = () => {
    login();
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#020e1a] via-[#000036] to-[#133e78] flex items-center justify-center p-4">
      {/* Background branding */}
      <div className="absolute inset-0 flex items-center justify-center opacity-5 pointer-events-none">
        <div className="w-96 h-96 bg-blue-500 rounded-full blur-3xl"></div>
      </div>

      {/* Login Card */}
      <div className="relative bg-gray-800/80 backdrop-blur-sm rounded-2xl p-8 max-w-md w-full border border-gray-700 shadow-2xl">
        {/* Logo area */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-gradient-to-br from-[#133e78] to-[#486c93] rounded-xl mx-auto mb-4 flex items-center justify-center shadow-lg">
            <svg
              className="w-8 h-8 text-white"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 10V3L4 14h7v7l9-11h-7z"
              />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-white mb-2">Asgard Basis</h1>
          <p className="text-gray-400">Automated yield farming strategy</p>
        </div>

        {/* Wallet setup info */}
        <div className="bg-gray-800/60 border border-[#cbd5e1]/20 rounded-lg p-4 mb-6">
          <p className="text-sm text-blue-200">
            We'll create both <strong>Solana</strong> and <strong>Arbitrum</strong> wallets for you automatically.
          </p>
        </div>

        {/* Features list */}
        <div className="space-y-3 mb-8">
          <div className="flex items-center gap-3 text-sm text-gray-300">
            <svg className="w-5 h-5 text-green-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span>Market-neutral yield generation</span>
          </div>
          <div className="flex items-center gap-3 text-sm text-gray-300">
            <svg className="w-5 h-5 text-green-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span>Automated position management</span>
          </div>
          <div className="flex items-center gap-3 text-sm text-gray-300">
            <svg className="w-5 h-5 text-green-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span>Built-in risk controls</span>
          </div>
        </div>

        {/* Login Button */}
        <button
          onClick={handleLogin}
          className="w-full py-3 px-4 bg-gradient-to-r from-[#133e78] to-[#1e4976] hover:from-[#1a4a8a] hover:to-[#255a8a] text-white font-medium rounded-lg transition-all transform hover:scale-[1.02] active:scale-[0.98] shadow-lg"
        >
          Get Started
        </button>

        {/* Security note */}
        <p className="text-center text-xs text-gray-500 mt-6">
          Secured by Privy. No private keys stored on our servers.
        </p>
      </div>
    </div>
  );
}
