"""
Dashboard module for BasisStrategy trading bot.

Provides web UI, API endpoints, and bot bridge functionality.
"""

# Re-export commonly used authentication functions
from src.dashboard.auth import (
    session_manager,
    get_current_session,
    get_current_user,
    require_csrf,
    get_encryption_manager,
    require_admin,
    require_operator,
    require_viewer,
    verify_api_key,
    PrivyAuth,
    User,
    Session,
)

# Re-export Privy SDK client
from src.dashboard.privy_client import (
    PrivyClient,
    get_privy_client,
    AuthenticationError,
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
    "session_manager",
    "get_current_session",
    "get_current_user",
    "require_csrf",
    "get_encryption_manager",
    "require_admin",
    "require_operator",
    "require_viewer",
    "verify_api_key",
    "PrivyAuth",
    "User",
    "Session",
    # Privy SDK
    "PrivyClient",
    "get_privy_client",
    "AuthenticationError",
    # Cache
    "cached",
    "TimedCache",
    # Bot Bridge
    "BotBridge",
    "BotUnavailableError",
]
