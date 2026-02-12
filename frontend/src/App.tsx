import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PrivyProvider } from '@privy-io/react-auth';
import { Layout } from './components/layout/Layout';
import { Dashboard } from './components/dashboard/Dashboard';
import { Settings } from './components/settings/Settings';
import { Positions } from './components/positions/Positions';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ToastContainer, GlobalLoading } from './components/ui';
import { useSSE } from './hooks';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30000, // 30 seconds
    },
  },
});

const privyAppId = import.meta.env.VITE_PRIVY_APP_ID || '';

// Debug: Log if app ID is missing
if (!privyAppId) {
  console.warn('⚠️ VITE_PRIVY_APP_ID is not set. Authentication will not work.');
}

// SSE initializer component
function SSEInitializer() {
  useSSE();
  return null;
}

function App() {
  // Show error if Privy app ID is not configured
  if (!privyAppId) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
        <div className="bg-gray-800 rounded-xl p-8 max-w-md w-full border border-red-700">
          <h1 className="text-2xl font-bold text-red-400 mb-4">Configuration Error</h1>
          <p className="text-gray-300 mb-4">
            Missing <code className="bg-gray-700 px-2 py-1 rounded">VITE_PRIVY_APP_ID</code>
          </p>
          <p className="text-sm text-gray-400">
            Please create a <code className="bg-gray-700 px-1 rounded">.env</code> file with:
          </p>
          <pre className="bg-gray-900 p-3 rounded mt-2 text-sm text-gray-300">
            VITE_PRIVY_APP_ID=your-privy-app-id
          </pre>
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <PrivyProvider
        appId={privyAppId}
        config={{
          loginMethods: ['email'],
          appearance: {
            theme: 'dark',
            accentColor: '#4a90d9',
          },
          embeddedWallets: {
            ethereum: {
              createOnLogin: 'all-users',
            },
            solana: {
              createOnLogin: 'all-users',
            },
          },
        }}
      >
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <SSEInitializer />
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/positions" element={<Positions />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </Layout>
            <ToastContainer />
            <GlobalLoading />
          </BrowserRouter>
        </QueryClientProvider>
      </PrivyProvider>
    </ErrorBoundary>
  );
}

export default App;
