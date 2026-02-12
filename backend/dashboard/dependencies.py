"""
Dashboard dependencies.
"""

from typing import Optional
from fastapi import HTTPException
from backend.dashboard.bot_bridge import BotBridge
from bot.core.position_monitor import PositionMonitorService
from bot.core.intent_scanner import IntentScanner

# Global bot bridge instance (set during lifespan)
_bot_bridge: Optional[BotBridge] = None

# Global position monitor instance (set during lifespan)
_position_monitor: Optional[PositionMonitorService] = None

# Global intent scanner instance (set during lifespan)
_intent_scanner: Optional[IntentScanner] = None


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


def set_position_monitor(monitor: PositionMonitorService):
    """Set the global position monitor instance."""
    global _position_monitor
    _position_monitor = monitor


def get_position_monitor() -> Optional[PositionMonitorService]:
    """Get the global position monitor instance."""
    return _position_monitor


def set_intent_scanner(scanner: IntentScanner):
    """Set the global intent scanner instance."""
    global _intent_scanner
    _intent_scanner = scanner


def get_intent_scanner() -> Optional[IntentScanner]:
    """Get the global intent scanner instance."""
    return _intent_scanner
