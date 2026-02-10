"""
Privy SDK client wrapper for authentication and user management.

Uses the official privy-client Python SDK for server-side operations.
"""

import os
from typing import Optional, Dict, Any
from pathlib import Path

from privy import AsyncPrivyAPI, PrivyAPI


class PrivyClient:
    """
    Wrapper around the official Privy Python SDK.
    
    Provides:
    - User authentication via access tokens
    - Wallet management
    - User information retrieval
    """
    
    def __init__(self, app_id: Optional[str] = None, app_secret: Optional[str] = None):
        """
        Initialize Privy client.
        
        Args:
            app_id: Privy app ID (or read from secrets/privy_app_id.txt)
            app_secret: Privy app secret (or read from secrets/privy_app_secret.txt)
        """
        self.app_id = app_id or self._load_secret("privy_app_id.txt")
        self.app_secret = app_secret or self._load_secret("privy_app_secret.txt")
        
        if not self.app_id or not self.app_secret:
            raise ValueError(
                "Privy credentials required. Set app_id/app_secret or "
                "store in secrets/privy_app_id.txt and secrets/privy_app_secret.txt"
            )
        
        # Initialize async client for FastAPI compatibility
        self._async_client: Optional[AsyncPrivyAPI] = None
        self._sync_client: Optional[PrivyAPI] = None
    
    def _load_secret(self, filename: str) -> Optional[str]:
        """Load secret from secrets directory."""
        secret_path = Path("secrets") / filename
        if secret_path.exists():
            return secret_path.read_text().strip()
        return None
    
    @property
    def async_client(self) -> AsyncPrivyAPI:
        """Get or create async client."""
        if self._async_client is None:
            self._async_client = AsyncPrivyAPI(
                app_id=self.app_id,
                app_secret=self.app_secret
            )
        return self._async_client
    
    @property
    def sync_client(self) -> PrivyAPI:
        """Get or create sync client."""
        if self._sync_client is None:
            self._sync_client = PrivyAPI(
                app_id=self.app_id,
                app_secret=self.app_secret
            )
        return self._sync_client
    
    async def verify_access_token(self, token: str) -> Dict[str, Any]:
        """
        Verify a Privy access token and return user information.
        
        Args:
            token: The Privy access token (from frontend)
            
        Returns:
            User data including id, email, wallet addresses
            
        Raises:
            AuthenticationError: If token is invalid
        """
        try:
            response = await self.async_client.users.verify_access_token(
                access_token=token
            )
            return {
                "id": response.user.id,
                "email": response.user.email if hasattr(response.user, 'email') else None,
                "wallet_address": response.user.wallet_address if hasattr(response.user, 'wallet_address') else None,
                "custom_metadata": response.user.custom_metadata if hasattr(response.user, 'custom_metadata') else {},
            }
        except Exception as e:
            raise AuthenticationError(f"Invalid Privy token: {e}") from e
    
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user information by ID.
        
        Args:
            user_id: Privy user ID
            
        Returns:
            User data or None if not found
        """
        try:
            user = await self.async_client.users.get(user_id=user_id)
            return {
                "id": user.id,
                "email": user.email if hasattr(user, 'email') else None,
                "wallet_address": user.wallet_address if hasattr(user, 'wallet_address') else None,
                "created_at": user.created_at if hasattr(user, 'created_at') else None,
            }
        except Exception:
            return None
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get user by email address.
        
        Args:
            email: User's email address
            
        Returns:
            User data or None if not found
        """
        try:
            user = await self.async_client.users.get_by_email_address(
                email_address=email
            )
            return {
                "id": user.id,
                "email": user.email if hasattr(user, 'email') else None,
                "wallet_address": user.wallet_address if hasattr(user, 'wallet_address') else None,
            }
        except Exception:
            return None
    
    async def list_users(self, limit: int = 100, cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        List users in the app.
        
        Args:
            limit: Maximum number of users to return
            cursor: Pagination cursor
            
        Returns:
            List of users and pagination info
        """
        response = await self.async_client.users.list(
            limit=limit,
            cursor=cursor
        )
        return {
            "users": [
                {
                    "id": user.id,
                    "email": user.email if hasattr(user, 'email') else None,
                }
                for user in response.data
            ],
            "next_cursor": response.next_cursor if hasattr(response, 'next_cursor') else None,
        }
    
    async def create_user_wallet(self, user_id: str, chain_type: str = "ethereum") -> Dict[str, Any]:
        """
        Create a wallet for a user.
        
        Args:
            user_id: Privy user ID
            chain_type: Blockchain type (ethereum, solana, etc.)
            
        Returns:
            Wallet information
        """
        response = await self.async_client.wallets.create(
            user_id=user_id,
            chain_type=chain_type
        )
        return {
            "id": response.id,
            "address": response.address,
            "chain_type": response.chain_type,
            "created_at": response.created_at if hasattr(response, 'created_at') else None,
        }
    
    async def get_user_wallets(self, user_id: str) -> list:
        """
        Get all wallets for a user.
        
        Args:
            user_id: Privy user ID
            
        Returns:
            List of wallet information
        """
        response = await self.async_client.wallets.list(user_id=user_id)
        return [
            {
                "id": wallet.id,
                "address": wallet.address,
                "chain_type": wallet.chain_type,
            }
            for wallet in response.data
        ]
    
    async def close(self):
        """Close the async client connection."""
        if self._async_client:
            await self._async_client.close()
            self._async_client = None


class AuthenticationError(Exception):
    """Raised when Privy authentication fails."""
    pass


# Singleton instance for reuse
_privy_client: Optional[PrivyClient] = None


def get_privy_client() -> PrivyClient:
    """Get or create the singleton Privy client instance."""
    global _privy_client
    if _privy_client is None:
        _privy_client = PrivyClient()
    return _privy_client


def reset_privy_client():
    """Reset the singleton (useful for testing)."""
    global _privy_client
    _privy_client = None
