"""
Event type definitions for WebSocket communication.
"""

from datetime import datetime
from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel


class SnapshotEvent(BaseModel):
    """Full state snapshot sent on WebSocket connection."""
    type: Literal["snapshot"] = "snapshot"
    seq: int
    timestamp: str
    data: Dict[str, Any]


class PositionUpdateEvent(BaseModel):
    """Position update event."""
    type: Literal["position_update"] = "position_update"
    seq: int
    timestamp: str
    data: Dict[str, Any]


class PauseStateChangeEvent(BaseModel):
    """Pause state change event."""
    type: Literal["pause_state_change"] = "pause_state_change"
    seq: int
    timestamp: str
    data: Dict[str, Any]


class TokenRefreshRequiredEvent(BaseModel):
    """Token refresh notification."""
    type: Literal["token_refresh_required"] = "token_refresh_required"
    timestamp: str
    refresh_url: str


class HeartbeatEvent(BaseModel):
    """WebSocket heartbeat."""
    type: Literal["heartbeat"] = "heartbeat"
    seq: int
    timestamp: str


class CatchUpEvent(BaseModel):
    """Catch-up events for reconnection."""
    type: Literal["catch_up"] = "catch_up"
    from_seq: int
    to_seq: int
    events: list


class ErrorEvent(BaseModel):
    """Error event for WebSocket."""
    type: Literal["error"] = "error"
    timestamp: str
    message: str
    code: Optional[str] = None
