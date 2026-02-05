"""
Dashboard dependencies.
"""

from typing import Optional
from fastapi import HTTPException
from src.dashboard.bot_bridge import BotBridge

# Global bot bridge instance (set during lifespan)
_bot_bridge: Optional[BotBridge] = None


def set_bot_bridge(bridge: BotBridge):
    """Set the global bot bridge instance."""
    global _bot_bridge
    _bot_bridge = bridge


def get_bot_bridge() -> Optional[BotBridge]:
    """Get the global bot bridge instance."""
    return _bot_bridge


def require_bot_bridge() -> BotBridge:
    """Require bot bridge to be initialized."""
    if _bot_bridge is None:
        raise HTTPException(503, "Dashboard not initialized")
    return _bot_bridge
