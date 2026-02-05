"""
Shared schemas and utilities for BasisStrategy.

Used by both the trading bot and dashboard.
"""

from src.shared.schemas import (
    PositionSummary,
    PositionDetail,
    BotStats,
    PauseState,
    HealthStatus,
    ControlCommand,
    ControlResponse,
)

from src.shared.events import (
    SnapshotEvent,
    PositionUpdateEvent,
    PauseStateChangeEvent,
    TokenRefreshRequiredEvent,
    HeartbeatEvent,
    CatchUpEvent,
    ErrorEvent,
)

__all__ = [
    # Schemas
    "PositionSummary",
    "PositionDetail", 
    "BotStats",
    "PauseState",
    "HealthStatus",
    "ControlCommand",
    "ControlResponse",
    # Events
    "SnapshotEvent",
    "PositionUpdateEvent",
    "PauseStateChangeEvent",
    "TokenRefreshRequiredEvent",
    "HeartbeatEvent",
    "CatchUpEvent",
    "ErrorEvent",
]
