"""
Shared Pydantic models for bot-dashboard communication.
These models are serializable and used in both services.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field, field_serializer


class BotState(str, Enum):
    """Bot operational states."""
    STARTING = "starting"
    RECOVERING = "recovering"
    RUNNING = "running"
    DEGRADED = "degraded"
    SHUTDOWN = "shutdown"


class PauseScope(str, Enum):
    """Pause operation scopes."""
    ALL = "all"
    ENTRY = "entry"
    EXIT = "exit"
    ASGARD = "asgard"
    HYPERLIQUID = "hyperliquid"


def serialize_decimal(value: Decimal) -> str:
    """Serialize Decimal to string for JSON."""
    return str(value)


class PositionSummary(BaseModel):
    """Lightweight position for list views."""
    
    position_id: str
    asset: str
    status: str
    leverage: Decimal
    deployed_usd: Decimal
    long_value_usd: Decimal
    short_value_usd: Decimal
    delta: Decimal
    delta_ratio: Decimal
    asgard_hf: Decimal
    hyperliquid_mf: Decimal
    total_pnl_usd: Decimal
    funding_pnl_usd: Decimal
    opened_at: datetime
    hold_duration_hours: float
    
    @field_serializer('leverage', 'deployed_usd', 'long_value_usd', 'short_value_usd',
                      'delta', 'delta_ratio', 'asgard_hf', 'hyperliquid_mf',
                      'total_pnl_usd', 'funding_pnl_usd')
    def serialize_decimals(self, value: Decimal) -> str:
        return str(value)


class PositionDetail(PositionSummary):
    """Full position details."""
    
    sizing: Dict[str, Decimal]
    asgard: Dict[str, Any]
    hyperliquid: Dict[str, Any]
    pnl: Dict[str, Decimal]
    risk: Dict[str, Any]


class BotStats(BaseModel):
    """Bot runtime statistics."""
    
    uptime_seconds: float
    uptime_formatted: str
    opportunities_found: int
    positions_opened: int
    positions_closed: int
    errors_count: int


class PauseState(BaseModel):
    """Current pause state."""
    
    paused: bool
    scope: PauseScope
    reason: Optional[str] = None
    paused_at: Optional[datetime] = None
    paused_by: Optional[str] = None
    active_breakers: List[str] = Field(default_factory=list)


class HealthStatus(BaseModel):
    """Combined health status."""
    
    status: str  # healthy, degraded, unhealthy
    timestamp: datetime
    version: str
    checks: Dict[str, Dict[str, Any]]


class ControlCommand(BaseModel):
    """Control command for bot operations."""
    
    command: str  # pause, resume, emergency_stop
    api_key: str
    reason: Optional[str] = None
    scope: Optional[str] = "all"


class ControlResponse(BaseModel):
    """Response from control command."""
    
    success: bool
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class User(BaseModel):
    """Dashboard user."""
    
    user_id: str
    role: str  # viewer, operator, admin
