import { describe, it, expect, beforeEach } from 'vitest';
import { useAuthStore } from '../authStore';

describe('authStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    const store = useAuthStore.getState();
    store.setUser(null);
    store.setAuthenticated(false);
    store.setLoading(false);
  });

  it('should have correct initial state', () => {
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isLoading).toBe(false);
  });

  it('should set user and authentication status', () => {
    const store = useAuthStore.getState();
    const mockUser = {
      id: 'user_123',
      email: 'test@example.com',
      wallets: [
        { address: '0x123', chainType: 'ethereum' as const, type: 'embedded' as const },
      ],
    };

    store.setUser(mockUser);
    store.setAuthenticated(true);

    const state = useAuthStore.getState();
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated).toBe(true);
  });

  it('should get Solana wallet', () => {
    const store = useAuthStore.getState();
    const mockUser = {
      id: 'user_123',
      wallets: [
        { address: 'sol123', chainType: 'solana' as const, type: 'embedded' as const },
        { address: '0x456', chainType: 'ethereum' as const, type: 'embedded' as const },
      ],
    };

    store.setUser(mockUser);

    const solanaWallet = store.getSolanaWallet();
    expect(solanaWallet).toEqual(mockUser.wallets[0]);
  });

  it('should get EVM wallet', () => {
    const store = useAuthStore.getState();
    const mockUser = {
      id: 'user_123',
      wallets: [
        { address: 'sol123', chainType: 'solana' as const, type: 'embedded' as const },
        { address: '0x456', chainType: 'ethereum' as const, type: 'embedded' as const },
      ],
    };

    store.setUser(mockUser);

    const evmWallet = store.getEvmWallet();
    expect(evmWallet).toEqual(mockUser.wallets[1]);
  });

  it('should logout and clear state', () => {
    const store = useAuthStore.getState();
    store.setUser({ id: 'user_123', wallets: [] });
    store.setAuthenticated(true);

    store.logout();

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });
});
