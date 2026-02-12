"""
Shared schemas and utilities for Asgard Basis.

Used by both the trading bot and dashboard.
"""

from shared.common.schemas import (
    PositionSummary,
    PositionDetail,
    BotStats,
    PauseState,
    HealthStatus,
    ControlCommand,
    ControlResponse,
)

from shared.common.events import (
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
