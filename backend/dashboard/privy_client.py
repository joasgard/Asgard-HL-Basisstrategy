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
        """Load secret from secrets directory (relative to project root)."""
        # Try relative to this file's location (backend/dashboard/ -> ../../secrets/)
        project_root = Path(__file__).resolve().parent.parent.parent
        secret_path = project_root / "secrets" / filename
        if secret_path.exists():
            return secret_path.read_text().strip()
        # Fallback: relative to cwd
        fallback = Path("secrets") / filename
        if fallback.exists():
            return fallback.read_text().strip()
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
            claims = await self.async_client.users.verify_access_token(
                auth_token=token
            )
            # claims is AccessTokenClaims TypedDict with user_id, app_id, etc.
            return {
                "id": claims["user_id"],
                "user_id": claims["user_id"],
            }
        except Exception as e:
            raise AuthenticationError(f"Invalid Privy token: {e}") from e
    
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user information by ID, including wallet addresses from linked accounts.

        Args:
            user_id: Privy user ID (did:privy:... format)

        Returns:
            User data with wallet addresses extracted from linked_accounts
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            user = await self.async_client.users.get(user_id=user_id)

            # Extract wallet addresses and email from linked_accounts
            email = None
            solana_address = None
            ethereum_address = None

            logger.info(f"Privy user {user_id}: {len(user.linked_accounts)} linked accounts")
            for account in user.linked_accounts:
                acct_type = getattr(account, 'type', None)
                chain_type = getattr(account, 'chain_type', None)
                address = getattr(account, 'address', None)
                logger.info(f"  linked_account: type={acct_type}, chain_type={chain_type}, address={address[:10] if address else None}...")

                # Email accounts
                if acct_type == 'email' and address:
                    email = address

                # Wallet accounts (both embedded and external)
                if chain_type == 'solana' and address and not solana_address:
                    solana_address = address
                elif chain_type == 'ethereum' and address and not ethereum_address:
                    ethereum_address = address

            logger.info(f"Extracted: email={email}, sol={solana_address}, evm={ethereum_address}")

            return {
                "id": user.id,
                "email": email,
                "solana_address": solana_address,
                "ethereum_address": ethereum_address,
                "created_at": user.created_at if hasattr(user, 'created_at') else None,
            }
        except Exception as e:
            logger.error(f"Failed to get Privy user {user_id}: {e}", exc_info=True)
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
            # Use get_user to properly extract linked_accounts
            return await self.get_user(user.id)
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
    
    async def get_user_wallet_addresses(self, user_id: str) -> Dict[str, Optional[str]]:
        """
        Get wallet addresses for a user from their Privy linked accounts.

        Wallets are created by the frontend Privy SDK (createOnLogin: 'all-users').
        This method reads them from the user's profile — it does NOT create wallets.

        Args:
            user_id: Privy user ID (did:privy:... format)

        Returns:
            Dict with 'solana_address' and 'ethereum_address' (either may be None)
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            user_data = await self.get_user(user_id)
        except Exception as e:
            logger.warning(f"Failed to fetch Privy user {user_id}: {e}")
            return {"solana_address": None, "ethereum_address": None}

        if not user_data:
            logger.warning(f"Could not fetch Privy user {user_id}")
            return {"solana_address": None, "ethereum_address": None}

        return {
            "solana_address": user_data.get("solana_address"),
            "ethereum_address": user_data.get("ethereum_address"),
        }

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
