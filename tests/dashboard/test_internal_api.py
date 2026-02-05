"""Tests for bot internal API."""

import pytest
from decimal import Decimal
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.core.internal_api import internal_app, set_bot_instance
from src.shared.schemas import PositionSummary, BotStats, PauseState


# Mock settings for authentication
@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings for all tests."""
    mock = MagicMock()
    mock.admin_api_key = "test_admin_key"
    # Patch where get_settings is used
    with patch('src.core.internal_api.get_settings', return_value=mock):
        yield mock


class MockAsgard:
    """Mock Asgard position data."""
    def __init__(self):
        self.asset = type('Asset', (), {'value': 'SOL'})()
        self.leverage = Decimal("2.5")
        self.collateral_usd = Decimal("1000.00")
        self.current_value_usd = Decimal("1000.00")
        self.current_health_factor = Decimal("1.5")
        self.pnl_usd = Decimal("5.00")
        self.position_pda = "test_pda_123"
        self.token_a_amount = Decimal("10.0")
        self.entry_price_token_a = Decimal("100.0")
        self.current_token_a_price = Decimal("102.0")


class MockHyperliquid:
    """Mock Hyperliquid position data."""
    def __init__(self):
        self.size_usd = Decimal("1000.00")
        self.size_sol = Decimal("10.0")
        self.entry_px = Decimal("100.0")
        self.mark_px = Decimal("102.0")
        self.leverage = Decimal("2.5")
        self.margin_used = Decimal("400.0")
        self.margin_fraction = Decimal("0.1")
        self.unrealized_pnl = Decimal("-3.00")


class MockPosition:
    """Mock CombinedPosition."""
    def __init__(self, position_id="pos_001"):
        self.position_id = position_id
        self.status = "open"
        self.asgard = MockAsgard()
        self.hyperliquid = MockHyperliquid()
        self.delta = Decimal("0.5")
        self.delta_ratio = Decimal("0.0005")
        self.total_pnl = Decimal("2.00")
        self.net_funding_pnl = Decimal("0.5")
        self.is_at_risk = False
        self.created_at = datetime.utcnow()


class MockStats:
    """Mock BotStats."""
    def __init__(self):
        self.start_time = datetime.utcnow()
        self.stop_time = None
        self.opportunities_found = 100
        self.positions_opened = 10
        self.positions_closed = 5
        self.errors = []
    
    @property
    def uptime_seconds(self):
        return 3600.0
    
    @property
    def uptime_formatted(self):
        return "01:00:00"


class MockPauseState:
    """Mock pause state."""
    def __init__(self):
        self.paused = False
        self.scope = type('Scope', (), {'value': 'all'})()
        self.reason = None
        self.paused_at = None
        self.paused_by = None
        self.active_breakers = []


class MockPauseController:
    """Mock pause controller."""
    def __init__(self):
        self._state = MockPauseState()
    
    def get_pause_state(self):
        return self._state
    
    def pause(self, api_key, reason, scope):
        self._state.paused = True
        self._state.reason = reason
        return True
    
    def resume(self, api_key):
        self._state.paused = False
        self._state.reason = None
        return True


class MockBot:
    """Mock DeltaNeutralBot for testing."""
    
    def __init__(self):
        self._running = True
        self._stats = MockStats()
        self._positions = {"pos_001": MockPosition("pos_001")}
        self._pause_controller = MockPauseController()
    
    def get_stats(self):
        return self._stats
    
    def get_positions(self):
        return self._positions
    
    async def pause(self, api_key, reason, scope):
        return self._pause_controller.pause(api_key, reason, scope)
    
    async def resume(self, api_key):
        return self._pause_controller.resume("test_key")


@pytest.fixture
def mock_bot():
    """Create a mock bot instance."""
    bot = MockBot()
    set_bot_instance(bot)
    return bot


@pytest.fixture
def client(mock_bot):
    """Create a test client with mock bot."""
    return TestClient(internal_app)


@pytest.fixture
def auth_headers(mock_settings):
    """Create authorization headers."""
    # Use the same key as the mock settings
    return {"Authorization": f"Bearer {mock_settings.admin_api_key}"}


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    def test_health_bot_running(self, client, mock_bot):
        """Health check returns healthy when bot is running."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["state"] == "running"
    
    def test_health_no_bot(self, client):
        """Health check returns starting when no bot instance."""
        set_bot_instance(None)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "starting"


class TestStatsEndpoint:
    """Test stats endpoint."""
    
    def test_get_stats_success(self, client, mock_bot, auth_headers):
        """Get stats returns correct data."""
        response = client.get("/internal/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["uptime_seconds"] == 3600.0
        assert data["uptime_formatted"] == "01:00:00"
        assert data["opportunities_found"] == 100
        assert data["positions_opened"] == 10
        assert data["positions_closed"] == 5
        assert data["errors_count"] == 0
    
    def test_get_stats_unauthorized(self, client):
        """Get stats without auth returns 401."""
        response = client.get("/internal/stats")
        assert response.status_code == 401  # FastAPI auto-bearer requires auth


class TestPositionsEndpoint:
    """Test positions endpoints."""
    
    def test_get_positions_success(self, client, mock_bot, auth_headers):
        """Get positions returns all positions."""
        response = client.get("/internal/positions", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "pos_001" in data
        pos = data["pos_001"]
        assert pos["asset"] == "SOL"
        assert pos["status"] == "open"
    
    def test_get_position_detail_success(self, client, mock_bot, auth_headers):
        """Get position detail returns full details."""
        response = client.get("/internal/positions/pos_001", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["position_id"] == "pos_001"
        assert "sizing" in data
        assert "asgard" in data
        assert "hyperliquid" in data
        assert "pnl" in data
        assert "risk" in data
    
    def test_get_position_detail_not_found(self, client, mock_bot, auth_headers):
        """Get non-existent position returns 404."""
        response = client.get("/internal/positions/nonexistent", headers=auth_headers)
        assert response.status_code == 404


class TestPauseStateEndpoint:
    """Test pause state endpoint."""
    
    def test_get_pause_state(self, client, mock_bot, auth_headers):
        """Get pause state returns current state."""
        response = client.get("/internal/pause-state", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["paused"] is False
        assert data["scope"] == "all"


class TestControlEndpoints:
    """Test control endpoints."""
    
    def test_pause_bot(self, client, mock_bot, auth_headers):
        """Pause bot returns success."""
        response = client.post(
            "/internal/control/pause",
            headers=auth_headers,
            json={
                "api_key": "test_key",
                "reason": "Testing pause",
                "scope": "all"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
    
    def test_resume_bot(self, client, mock_bot, auth_headers):
        """Resume bot returns success."""
        response = client.post(
            "/internal/control/resume",
            headers=auth_headers,
            json={"api_key": "test_key"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
