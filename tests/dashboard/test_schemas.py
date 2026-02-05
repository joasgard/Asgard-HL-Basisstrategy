"""Tests for shared schemas."""

import pytest
from datetime import datetime
from decimal import Decimal
from src.shared.schemas import (
    BotState,
    PauseScope,
    PositionSummary,
    PositionDetail,
    BotStats,
    PauseState,
    HealthStatus,
    ControlCommand,
    ControlResponse,
)


class TestBotState:
    """Test BotState enum."""
    
    def test_bot_state_values(self):
        assert BotState.STARTING == "starting"
        assert BotState.RECOVERING == "recovering"
        assert BotState.RUNNING == "running"
        assert BotState.DEGRADED == "degraded"
        assert BotState.SHUTDOWN == "shutdown"
    
    def test_bot_state_serialization(self):
        assert BotState.RUNNING.value == "running"


class TestPauseScope:
    """Test PauseScope enum."""
    
    def test_pause_scope_values(self):
        assert PauseScope.ALL == "all"
        assert PauseScope.ENTRY == "entry"
        assert PauseScope.EXIT == "exit"
        assert PauseScope.ASGARD == "asgard"
        assert PauseScope.HYPERLIQUID == "hyperliquid"


class TestPositionSummary:
    """Test PositionSummary schema."""
    
    def test_position_summary_creation(self):
        pos = PositionSummary(
            position_id="pos_20250204000001",
            asset="SOL",
            status="open",
            leverage=Decimal("2.5"),
            deployed_usd=Decimal("1000.00"),
            long_value_usd=Decimal("1000.00"),
            short_value_usd=Decimal("1000.00"),
            delta=Decimal("0.00"),
            delta_ratio=Decimal("0.0001"),
            asgard_hf=Decimal("1.5"),
            hyperliquid_mf=Decimal("0.1"),
            total_pnl_usd=Decimal("10.50"),
            funding_pnl_usd=Decimal("5.25"),
            opened_at=datetime.utcnow(),
            hold_duration_hours=24.5,
        )
        assert pos.position_id == "pos_20250204000001"
        assert pos.asset == "SOL"
        assert pos.leverage == Decimal("2.5")
    
    def test_decimal_serialization_as_string(self):
        """Decimals must serialize as strings, not floats."""
        pos = PositionSummary(
            position_id="pos_001",
            asset="SOL",
            status="open",
            leverage=Decimal("2.5"),
            deployed_usd=Decimal("1000.00"),
            long_value_usd=Decimal("1000.00"),
            short_value_usd=Decimal("1000.00"),
            delta=Decimal("0.00"),
            delta_ratio=Decimal("0.0001"),
            asgard_hf=Decimal("1.5"),
            hyperliquid_mf=Decimal("0.1"),
            total_pnl_usd=Decimal("10.50"),
            funding_pnl_usd=Decimal("5.25"),
            opened_at=datetime.utcnow(),
            hold_duration_hours=24.5,
        )
        data = pos.model_dump(mode="json")
        
        # All Decimals should be strings
        assert isinstance(data["leverage"], str)
        assert isinstance(data["deployed_usd"], str)
        assert isinstance(data["delta"], str)
        
        # Verify precision is preserved
        assert data["leverage"] == "2.5"
        assert data["delta"] == "0.00"


class TestPositionDetail:
    """Test PositionDetail schema."""
    
    def test_position_detail_creation(self):
        detail = PositionDetail(
            position_id="pos_001",
            asset="SOL",
            status="open",
            leverage=Decimal("2.5"),
            deployed_usd=Decimal("1000.00"),
            long_value_usd=Decimal("1000.00"),
            short_value_usd=Decimal("1000.00"),
            delta=Decimal("0.00"),
            delta_ratio=Decimal("0.0001"),
            asgard_hf=Decimal("1.5"),
            hyperliquid_mf=Decimal("0.1"),
            total_pnl_usd=Decimal("10.50"),
            funding_pnl_usd=Decimal("5.25"),
            opened_at=datetime.utcnow(),
            hold_duration_hours=24.5,
            sizing={"position_size_usd": Decimal("1000")},
            asgard={"position_pda": "abc123"},
            hyperliquid={"size_sol": Decimal("10")},
            pnl={"total_pnl": Decimal("10.50")},
            risk={"health_status": "healthy"},
        )
        assert detail.position_id == "pos_001"
        assert detail.asgard["position_pda"] == "abc123"


class TestBotStats:
    """Test BotStats schema."""
    
    def test_bot_stats_creation(self):
        stats = BotStats(
            uptime_seconds=86400.0,
            uptime_formatted="24:00:00",
            opportunities_found=100,
            positions_opened=10,
            positions_closed=5,
            errors_count=2,
        )
        assert stats.uptime_seconds == 86400.0
        assert stats.uptime_formatted == "24:00:00"


class TestPauseState:
    """Test PauseState schema."""
    
    def test_pause_state_creation(self):
        state = PauseState(
            paused=True,
            scope=PauseScope.ALL,
            reason="Manual pause",
            paused_at=datetime.utcnow(),
            paused_by="admin",
            active_breakers=["circuit_breaker"],
        )
        assert state.paused is True
        assert state.scope == PauseScope.ALL
        assert state.paused_by == "admin"
    
    def test_pause_state_defaults(self):
        state = PauseState(paused=False, scope=PauseScope.ALL)
        assert state.reason is None
        assert state.paused_at is None
        assert state.active_breakers == []


class TestHealthStatus:
    """Test HealthStatus schema."""
    
    def test_health_status_creation(self):
        status = HealthStatus(
            status="healthy",
            timestamp=datetime.utcnow(),
            version="1.0.0",
            checks={
                "database": {"status": "healthy"},
                "blockchain": {"status": "healthy"},
            },
        )
        assert status.status == "healthy"
        assert "database" in status.checks


class TestControlCommand:
    """Test ControlCommand schema."""
    
    def test_control_command_creation(self):
        cmd = ControlCommand(
            command="pause",
            api_key="test_key",
            reason="Testing",
            scope="all",
        )
        assert cmd.command == "pause"
        assert cmd.api_key == "test_key"


class TestControlResponse:
    """Test ControlResponse schema."""
    
    def test_control_response_creation(self):
        resp = ControlResponse(
            success=True,
            message="Operation completed",
        )
        assert resp.success is True
        assert resp.message == "Operation completed"
        assert resp.timestamp is not None
