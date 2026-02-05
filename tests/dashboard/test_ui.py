"""Tests for HTML UI endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock

from src.dashboard.main import create_app
from src.dashboard.dependencies import set_bot_bridge


@pytest.fixture
def mock_bot_bridge():
    """Create a mock bot bridge."""
    bridge = MagicMock()
    bridge.health_check = AsyncMock(return_value=True)
    bridge.get_stats = AsyncMock(return_value=MagicMock(
        uptime_seconds=3600.0,
        uptime_formatted="01:00:00",
        opportunities_found=100,
        positions_opened=10,
        positions_closed=5,
        errors_count=2,
    ))
    bridge.get_pause_state = AsyncMock(return_value=MagicMock(
        paused=False,
        scope="all",
        reason=None,
        paused_at=None,
        paused_by=None,
        active_breakers=[],
    ))
    bridge.get_positions = AsyncMock(return_value=[])
    return bridge


@pytest.fixture
def app(mock_bot_bridge):
    """Create test app."""
    set_bot_bridge(mock_bot_bridge)
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestDashboardPage:
    """Test dashboard HTML page."""
    
    def test_dashboard_page_loads(self, client):
        """Dashboard page renders without error."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert b"Delta Neutral Bot" in response.content
    
    def test_dashboard_contains_status_cards(self, client):
        """Dashboard contains status cards."""
        response = client.get("/")
        assert b"Uptime" in response.content
        assert b"Open Positions" in response.content
        assert b"Total PnL" in response.content
        assert b"Status" in response.content
    
    def test_dashboard_contains_control_panel(self, client):
        """Dashboard contains control panel."""
        response = client.get("/")
        assert b"Control Panel" in response.content
        assert b"Pause Entry" in response.content
        assert b"Pause All" in response.content
        assert b"Resume" in response.content


class TestPositionsPage:
    """Test positions HTML page."""
    
    def test_positions_page_loads(self, client):
        """Positions page renders without error."""
        response = client.get("/positions")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert b"Positions" in response.content
    
    def test_positions_contains_table(self, client):
        """Positions page contains table headers."""
        response = client.get("/positions")
        assert b"Asset" in response.content
        assert b"Status" in response.content
        assert b"PnL" in response.content
