import { apiClient } from './client';

export interface AuthStatusResponse {
  authenticated: boolean;
  user: {
    user_id: string;
    email?: string;
    solana_address?: string;
    evm_address?: string;
    is_new_user: boolean;
    created_at?: string;
  } | null;
}

export interface UserInfoResponse {
  user_id: string;
  email?: string;
  solana_address?: string;
  evm_address?: string;
  is_new_user: boolean;
  created_at?: string;
}

export interface PrivySyncRequest {
  privy_access_token: string;
  email?: string;
}

export interface PrivySyncResponse {
  success: boolean;
  user_id: string;
  email?: string;
  solana_address?: string;
  evm_address?: string;
  is_new_user: boolean;
}

/**
 * Check authentication status with backend
 * Uses cookie-based session
 */
export async function checkAuthStatus(): Promise<AuthStatusResponse> {
  const response = await apiClient.get('/auth/check');
  return response.data;
}

/**
 * Get current user info from backend
 */
export async function getCurrentUser(): Promise<UserInfoResponse> {
  const response = await apiClient.get('/auth/me');
  return response.data;
}

/**
 * Logout from backend (clears session cookie)
 */
export async function logoutBackend(): Promise<void> {
  await apiClient.post('/auth/logout');
}

/**
 * Sync Privy user with backend session
 * Creates/updates user and establishes session
 */
export async function syncPrivyAuth(accessToken: string, email?: string): Promise<PrivySyncResponse> {
  const response = await apiClient.post('/auth/sync', {
    privy_access_token: accessToken,
    email,
  });
  return response.data;
}
