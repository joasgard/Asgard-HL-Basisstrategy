"""Tests for status API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.dashboard.main import create_app
from src.dashboard.dependencies import get_bot_bridge, set_bot_bridge
from src.shared.schemas import BotStats, PauseState, User


@pytest.fixture
def mock_bot_bridge():
    """Create a mock bot bridge."""
    bridge = MagicMock()
    bridge.health_check = AsyncMock(return_value=True)
    bridge.get_stats = AsyncMock(return_value=BotStats(
        uptime_seconds=3600.0,
        uptime_formatted="01:00:00",
        opportunities_found=100,
        positions_opened=10,
        positions_closed=5,
        errors_count=2,
    ))
    bridge.get_pause_state = AsyncMock(return_value=PauseState(
        paused=False,
        scope="all",
        reason=None,
        paused_at=None,
        paused_by=None,
        active_breakers=[],
    ))
    return bridge


@pytest.fixture
def app():
    """Create test app."""
    return create_app()


@pytest.fixture(autouse=True)
def setup_bridge(mock_bot_bridge):
    """Setup mock bridge for each test."""
    set_bot_bridge(mock_bot_bridge)
    yield
    set_bot_bridge(None)


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    def test_health_check_public(self, client):
        """Health check is public."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["bot_connected"] is True
    
    def test_health_check_api_path(self, client):
        """Health check also available at API path."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200


class TestStatusEndpoint:
    """Test status endpoint."""
    
    def test_status_requires_auth(self, client):
        """Status requires authentication."""
        response = client.get("/api/v1/status")
        assert response.status_code == 401  # FastAPI bearer auth


class TestStatsEndpoint:
    """Test stats endpoint."""
    
    def test_stats_requires_auth(self, client):
        """Stats requires authentication."""
        response = client.get("/api/v1/stats")
        assert response.status_code == 401


class TestPauseStateEndpoint:
    """Test pause state endpoint."""
    
    def test_pause_state_requires_auth(self, client):
        """Pause state requires authentication."""
        response = client.get("/api/v1/pause-state")
        assert response.status_code == 401
