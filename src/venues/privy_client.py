"""
Shared Privy client configuration.

Provides a singleton Privy client instance for use across the application.
"""
from functools import lru_cache

from src.config.settings import get_settings


@lru_cache()
def get_privy_client():
    """
    Get or create singleton Privy client instance.
    
    Returns:
        Configured PrivyClient instance
    """
    # Import here to allow mocking in tests and optional dependency
    from privy import PrivyClient
    
    settings = get_settings()
    
    return PrivyClient(
        app_id=settings.privy_app_id,
        app_secret=settings.privy_app_secret,
        authorization_private_key_path=settings.privy_auth_key_path
    )
