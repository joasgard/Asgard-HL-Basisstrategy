"""
Dashboard module for BasisStrategy trading bot.

Provides web UI, API endpoints, and bot bridge functionality.
"""

# Re-export commonly used authentication functions
from src.dashboard.auth import (
    authenticate_user,
    create_access_token,
    verify_token,
    verify_api_key,
    require_admin,
    require_operator,
    require_viewer,
    get_current_user,
    User,
    TokenData,
)

# Re-export cache utilities
from src.dashboard.cache import (
    cached,
    TimedCache,
)

# Re-export bot bridge
from src.dashboard.bot_bridge import (
    BotBridge,
    BotUnavailableError,
)

# Version
__version__ = "1.0.0"

__all__ = [
    # Auth
    "authenticate_user",
    "create_access_token", 
    "verify_token",
    "verify_api_key",
    "require_admin",
    "require_operator",
    "require_viewer",
    "get_current_user",
    "User",
    "TokenData",
    # Cache
    "cached",
    "TimedCache",
    # Bot Bridge
    "BotBridge",
    "BotUnavailableError",
]
