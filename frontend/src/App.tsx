import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PrivyProvider } from '@privy-io/react-auth';
import { AuthWrapper } from './components/auth/AuthWrapper';
import { Layout } from './components/layout/Layout';
import { Dashboard } from './components/dashboard/Dashboard';
import { Settings } from './components/settings/Settings';
import { Positions } from './components/positions/Positions';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const privyAppId = import.meta.env.VITE_PRIVY_APP_ID || '';

function App() {
  return (
    <PrivyProvider
      appId={privyAppId}
      config={{
        loginMethods: ['email'],
        appearance: {
          theme: 'dark',
          accentColor: '#3b82f6',
        },
        embeddedWallets: {
          ethereum: {
            createOnLogin: 'users-without-wallets',
          },
          solana: {
            createOnLogin: 'users-without-wallets',
          },
        },
      }}
    >
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthWrapper>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/positions" element={<Positions />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </Layout>
          </AuthWrapper>
        </BrowserRouter>
      </QueryClientProvider>
    </PrivyProvider>
  );
}

export default App;
