import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface Wallet {
  address: string;
  chainType: 'solana' | 'ethereum';
  type: 'embedded' | 'external';
}

interface User {
  id: string;
  email?: string;
  wallets: Wallet[];
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  
  // Actions
  setUser: (user: User | null) => void;
  setAuthenticated: (value: boolean) => void;
  setLoading: (value: boolean) => void;
  getSolanaWallet: () => Wallet | undefined;
  getEvmWallet: () => Wallet | undefined;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isLoading: true,

      setUser: (user) => set({ user, isAuthenticated: !!user }),
      setAuthenticated: (value) => set({ isAuthenticated: value }),
      setLoading: (value) => set({ isLoading: value }),
      
      getSolanaWallet: () => {
        const { user } = get();
        return user?.wallets.find(w => w.chainType === 'solana');
      },
      
      getEvmWallet: () => {
        const { user } = get();
        return user?.wallets.find(w => w.chainType === 'ethereum');
      },
      
      logout: () => set({ user: null, isAuthenticated: false }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ 
        user: state.user, 
        isAuthenticated: state.isAuthenticated 
      }),
    }
  )
);
