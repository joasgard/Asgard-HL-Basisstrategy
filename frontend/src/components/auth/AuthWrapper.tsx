import { usePrivy } from '@privy-io/react-auth';
import { LoginPage } from './LoginPage';

interface AuthWrapperProps {
  children: React.ReactNode;
}

export function AuthWrapper({ children }: AuthWrapperProps) {
  const { authenticated, ready } = usePrivy();

  if (!ready) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (!authenticated) {
    return <LoginPage />;
  }

  return <>{children}</>;
}
