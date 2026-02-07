"""
Tests for dashboard status API (health, status, stats, pause-state).
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from fastapi import HTTPException


class TestHealthCheck:
    """Tests for GET /health endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.status.get_bot_bridge')
    async def test_health_healthy(self, mock_get_bridge):
        """Test health check when both services are healthy."""
        from src.dashboard.api.status import api_health_check
        
        mock_bridge = AsyncMock()
        mock_bridge.health_check.return_value = True
        mock_get_bridge.return_value = mock_bridge
        
        result = await api_health_check()
        
        assert result["dashboard"]["status"] == "healthy"
        assert result["bot"]["status"] == "healthy"
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.status.get_bot_bridge')
    async def test_health_bot_unavailable(self, mock_get_bridge):
        """Test health check when bot is unavailable."""
        from src.dashboard.api.status import api_health_check
        
        mock_bridge = AsyncMock()
        mock_bridge.health_check.return_value = False
        mock_get_bridge.return_value = mock_bridge
        
        result = await api_health_check()
        
        assert result["dashboard"]["status"] == "healthy"
        assert result["bot"]["status"] == "unavailable"
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.status.get_bot_bridge')
    async def test_health_bot_exception(self, mock_get_bridge):
        """Test health check when bot throws exception."""
        from src.dashboard.api.status import api_health_check
        
        mock_bridge = AsyncMock()
        mock_bridge.health_check.side_effect = Exception("Connection error")
        mock_get_bridge.return_value = mock_bridge
        
        result = await api_health_check()
        
        assert result["dashboard"]["status"] == "healthy"
        assert result["bot"]["status"] == "unavailable"


class TestGetStatus:
    """Tests for GET /status endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.status.require_bot_bridge')
    async def test_get_status_success(self, mock_require_bridge):
        """Test getting detailed bot status."""
        from src.dashboard.api.status import get_status
        from src.shared.schemas import BotStats, PauseState, PauseScope
        
        mock_bridge = AsyncMock()
        
        # Mock stats
        mock_stats = BotStats(
            uptime_seconds=3600,
            uptime_formatted="1h 0m",
            opportunities_found=10,
            positions_opened=5,
            positions_closed=3,
            errors_count=0
        )
        mock_bridge.get_stats.return_value = mock_stats
        
        # Mock pause state
        mock_pause = PauseState(
            paused=False,
            scope=PauseScope.ALL,
            reason=None,
            paused_at=None,
            paused_by=None,
            active_breakers=[]
        )
        mock_bridge.get_pause_state.return_value = mock_pause
        
        mock_require_bridge.return_value = mock_bridge
        
        result = await get_status()
        
        assert result["bot"]["running"] is True
        assert result["bot"]["uptime_seconds"] == 3600
        assert result["stats"]["opportunities_found"] == 10
        assert result["stats"]["positions_opened"] == 5
        assert result["pause_state"]["paused"] is False
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.status.require_bot_bridge')
    async def test_get_status_paused(self, mock_require_bridge):
        """Test status when bot is paused."""
        from src.dashboard.api.status import get_status
        from src.shared.schemas import BotStats, PauseState, PauseScope
        
        mock_bridge = AsyncMock()
        
        mock_stats = BotStats(
            uptime_seconds=7200,
            uptime_formatted="2h 0m",
            opportunities_found=20,
            positions_opened=8,
            positions_closed=5,
            errors_count=1
        )
        mock_bridge.get_stats.return_value = mock_stats
        
        mock_pause = PauseState(
            paused=True,
            scope=PauseScope.ENTRY,
            reason="Maintenance",
            paused_at=datetime.utcnow(),
            paused_by="admin",
            active_breakers=["circuit_breaker"]
        )
        mock_bridge.get_pause_state.return_value = mock_pause
        
        mock_require_bridge.return_value = mock_bridge
        
        result = await get_status()
        
        assert result["pause_state"]["paused"] is True
        assert result["pause_state"]["scope"] == "entry"
        assert result["pause_state"]["reason"] == "Maintenance"
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.status.require_bot_bridge')
    async def test_get_status_exception(self, mock_require_bridge):
        """Test handling exception when getting status."""
        from src.dashboard.api.status import get_status
        
        mock_bridge = AsyncMock()
        mock_bridge.get_stats.side_effect = Exception("Connection error")
        mock_require_bridge.return_value = mock_bridge
        
        with pytest.raises(HTTPException) as exc_info:
            await get_status()
        
        assert exc_info.value.status_code == 503


class TestGetStats:
    """Tests for GET /stats endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.status.require_bot_bridge')
    async def test_get_stats_success(self, mock_require_bridge):
        """Test getting bot statistics."""
        from src.dashboard.api.status import get_stats
        from src.shared.schemas import BotStats
        
        mock_bridge = AsyncMock()
        
        mock_stats = BotStats(
            uptime_seconds=86400,
            uptime_formatted="1d 0h",
            opportunities_found=100,
            positions_opened=25,
            positions_closed=20,
            errors_count=2
        )
        mock_bridge.get_stats.return_value = mock_stats
        mock_require_bridge.return_value = mock_bridge
        
        result = await get_stats()
        
        assert result["uptime_seconds"] == 86400
        assert result["opportunities_found"] == 100
        assert result["positions_opened"] == 25
        assert result["positions_closed"] == 20
        assert result["errors_count"] == 2
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.status.require_bot_bridge')
    async def test_get_stats_exception(self, mock_require_bridge):
        """Test handling exception when getting stats."""
        from src.dashboard.api.status import get_stats
        
        mock_bridge = AsyncMock()
        mock_bridge.get_stats.side_effect = Exception("Connection error")
        mock_require_bridge.return_value = mock_bridge
        
        with pytest.raises(HTTPException) as exc_info:
            await get_stats()
        
        assert exc_info.value.status_code == 503


class TestGetPauseState:
    """Tests for GET /pause-state endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.status.require_bot_bridge')
    async def test_get_pause_state_running(self, mock_require_bridge):
        """Test getting pause state when running."""
        from src.dashboard.api.status import get_pause_state
        from src.shared.schemas import PauseState, PauseScope
        
        mock_bridge = AsyncMock()
        
        mock_pause = PauseState(
            paused=False,
            scope=PauseScope.ALL,
            reason=None,
            paused_at=None,
            paused_by=None,
            active_breakers=[]
        )
        mock_bridge.get_pause_state.return_value = mock_pause
        mock_require_bridge.return_value = mock_bridge
        
        result = await get_pause_state()
        
        assert result["paused"] is False
        assert result["scope"] == "all"
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.status.require_bot_bridge')
    async def test_get_pause_state_paused(self, mock_require_bridge):
        """Test getting pause state when paused."""
        from src.dashboard.api.status import get_pause_state
        from src.shared.schemas import PauseState, PauseScope
        
        mock_bridge = AsyncMock()
        
        paused_at = datetime.utcnow()
        mock_pause = PauseState(
            paused=True,
            scope=PauseScope.ASGARD,
            reason="Rate limit hit",
            paused_at=paused_at,
            paused_by="system",
            active_breakers=["rate_limit"]
        )
        mock_bridge.get_pause_state.return_value = mock_pause
        mock_require_bridge.return_value = mock_bridge
        
        result = await get_pause_state()
        
        assert result["paused"] is True
        assert result["scope"] == "asgard"
        assert result["reason"] == "Rate limit hit"
        assert result["paused_by"] == "system"
        assert "rate_limit" in result["active_breakers"]
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.status.require_bot_bridge')
    async def test_get_pause_state_exception(self, mock_require_bridge):
        """Test handling exception when getting pause state."""
        from src.dashboard.api.status import get_pause_state
        
        mock_bridge = AsyncMock()
        mock_bridge.get_pause_state.side_effect = Exception("Connection error")
        mock_require_bridge.return_value = mock_bridge
        
        with pytest.raises(HTTPException) as exc_info:
            await get_pause_state()
        
        assert exc_info.value.status_code == 503
