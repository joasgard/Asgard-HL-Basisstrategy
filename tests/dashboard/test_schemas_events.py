"""Tests for event schemas."""

import pytest
from datetime import datetime
from src.shared.events import (
    SnapshotEvent,
    PositionUpdateEvent,
    PauseStateChangeEvent,
    TokenRefreshRequiredEvent,
    HeartbeatEvent,
    CatchUpEvent,
    ErrorEvent,
)


class TestSnapshotEvent:
    """Test SnapshotEvent."""
    
    def test_snapshot_event_creation(self):
        event = SnapshotEvent(
            seq=1,
            timestamp=datetime.utcnow().isoformat(),
            data={"positions": [], "stats": {}},
        )
        assert event.type == "snapshot"
        assert event.seq == 1
    
    def test_snapshot_event_default_type(self):
        event = SnapshotEvent(
            seq=1,
            timestamp="2024-01-01T00:00:00",
            data={},
        )
        assert event.type == "snapshot"


class TestPositionUpdateEvent:
    """Test PositionUpdateEvent."""
    
    def test_position_update_event_creation(self):
        event = PositionUpdateEvent(
            seq=2,
            timestamp=datetime.utcnow().isoformat(),
            data={"position_id": "pos_001", "status": "closed"},
        )
        assert event.type == "position_update"


class TestPauseStateChangeEvent:
    """Test PauseStateChangeEvent."""
    
    def test_pause_state_change_event_creation(self):
        event = PauseStateChangeEvent(
            seq=3,
            timestamp=datetime.utcnow().isoformat(),
            data={"paused": True, "reason": "Manual"},
        )
        assert event.type == "pause_state_change"


class TestHeartbeatEvent:
    """Test HeartbeatEvent."""
    
    def test_heartbeat_event_creation(self):
        event = HeartbeatEvent(
            seq=100,
            timestamp=datetime.utcnow().isoformat(),
        )
        assert event.type == "heartbeat"
        assert event.seq == 100


class TestCatchUpEvent:
    """Test CatchUpEvent."""
    
    def test_catch_up_event_creation(self):
        event = CatchUpEvent(
            from_seq=10,
            to_seq=20,
            events=[{"type": "position_update"}],
        )
        assert event.type == "catch_up"
        assert event.from_seq == 10
        assert event.to_seq == 20


class TestErrorEvent:
    """Test ErrorEvent."""
    
    def test_error_event_creation(self):
        event = ErrorEvent(
            timestamp=datetime.utcnow().isoformat(),
            message="Connection failed",
            code="WS_ERROR",
        )
        assert event.type == "error"
        assert event.message == "Connection failed"
    
    def test_error_event_optional_code(self):
        event = ErrorEvent(
            timestamp="2024-01-01T00:00:00",
            message="Unknown error",
        )
        assert event.code is None
