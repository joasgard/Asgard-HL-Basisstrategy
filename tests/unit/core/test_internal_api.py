"""
Tests for core internal API.
"""
import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from bot.core.internal_api import (
    internal_app, set_bot_instance, get_bot, verify_internal_token,
    health_check, _get_bot_state, get_stats, get_positions, get_position_detail,
    get_pause_state, pause_bot, resume_bot, open_position_internal,
    _position_to_summary, _position_to_detail
)
from shared.common.schemas import BotStats, PositionSummary, PositionDetail, PauseState


class TestSetBotInstance:
    """Tests for set_bot_instance function."""
    
    def test_set_bot_instance(self):
        """Test setting bot instance."""
        mock_bot = MagicMock()
        
        set_bot_instance(mock_bot)
        
        # Import after setting to get the updated value
        from bot.core.internal_api import _bot_instance
        assert _bot_instance is mock_bot
        
        # Reset for other tests
        set_bot_instance(None)


class TestGetBot:
    """Tests for get_bot function."""
    
    def test_get_bot_initialized(self):
        """Test getting bot when initialized."""
        mock_bot = MagicMock()
        set_bot_instance(mock_bot)
        
        bot = get_bot()
        
        assert bot is mock_bot
        
        set_bot_instance(None)
    
    def test_get_bot_not_initialized(self):
        """Test getting bot when not initialized raises 503."""
        set_bot_instance(None)
        
        with pytest.raises(HTTPException) as exc_info:
            get_bot()
        
        assert exc_info.value.status_code == 503
        assert "Bot not initialized" in exc_info.value.detail


class TestVerifyInternalToken:
    """Tests for verify_internal_token function."""
    
    def test_verify_valid_token(self, tmp_path):
        """Test verifying valid token."""
        secret_file = tmp_path / "server_secret.txt"
        secret_file.write_text("valid_token\n")

        with patch('shared.config.settings.SECRETS_DIR', tmp_path):
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="valid_token"
            )

            result = verify_internal_token(credentials)

            assert result == "valid_token"

    def test_verify_invalid_token(self, tmp_path):
        """Test verifying invalid token raises 401."""
        secret_file = tmp_path / "server_secret.txt"
        secret_file.write_text("valid_token\n")

        with patch('shared.config.settings.SECRETS_DIR', tmp_path):
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="invalid_token"
            )

            with pytest.raises(HTTPException) as exc_info:
                verify_internal_token(credentials)

            assert exc_info.value.status_code == 401
            assert "Invalid internal token" in exc_info.value.detail


class TestHealthCheck:
    """Tests for health_check endpoint."""
    
    @pytest.mark.asyncio
    async def test_health_bot_not_initialized(self):
        """Test health check when bot not initialized."""
        set_bot_instance(None)
        
        result = await health_check()
        
        assert result["status"] == "starting"
    
    @pytest.mark.asyncio
    async def test_health_bot_running(self):
        """Test health check when bot running."""
        # Use a simple class instead of MagicMock to avoid auto-attr issues
        class MockBot:
            _running = True
        
        set_bot_instance(MockBot())
        
        result = await health_check()
        
        assert result["status"] == "healthy"
        assert result["state"] == "running"
        
        set_bot_instance(None)
    
    @pytest.mark.asyncio
    async def test_health_bot_stopped(self):
        """Test health check when bot stopped."""
        class MockBot:
            _running = False
        
        set_bot_instance(MockBot())
        
        result = await health_check()
        
        assert result["status"] == "stopped"
        
        set_bot_instance(None)


class TestGetBotState:
    """Tests for _get_bot_state function."""
    
    def test_get_bot_state_starting(self):
        """Test state when bot not initialized."""
        set_bot_instance(None)
        
        state = _get_bot_state()
        
        assert state == "starting"
    
    def test_get_bot_state_shutdown(self):
        """Test state when bot not running."""
        mock_bot = MagicMock()
        mock_bot._running = False
        set_bot_instance(mock_bot)
        
        state = _get_bot_state()
        
        assert state == "shutdown"
        set_bot_instance(None)
    
    def test_get_bot_state_recovering(self):
        """Test state when bot recovering."""
        mock_bot = MagicMock()
        mock_bot._running = True
        mock_bot._recovering = True
        set_bot_instance(mock_bot)
        
        state = _get_bot_state()
        
        assert state == "recovering"
        set_bot_instance(None)
    
    def test_get_bot_state_running(self):
        """Test state when bot running normally."""
        mock_bot = MagicMock()
        mock_bot._running = True
        mock_bot._recovering = False
        # Explicitly set to False to avoid MagicMock returning a new mock
        del mock_bot._recovering  # Remove to avoid attribute exists check
        set_bot_instance(mock_bot)
        
        state = _get_bot_state()
        
        assert state == "running"
        set_bot_instance(None)


class TestGetStats:
    """Tests for get_stats endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_stats_success(self):
        """Test getting stats successfully."""
        mock_bot = MagicMock()
        mock_stats = MagicMock()
        mock_stats.uptime_seconds = 3600.5
        mock_stats.uptime_formatted = "1h 0m"
        mock_stats.opportunities_found = 10
        mock_stats.positions_opened = 5
        mock_stats.positions_closed = 3
        mock_stats.errors = ["error1", "error2"]
        mock_bot.get_stats.return_value = mock_stats
        set_bot_instance(mock_bot)
        
        with patch('bot.core.internal_api.verify_internal_token'):
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            result = await get_stats(credentials)
        
        assert result.uptime_seconds == 3600.5
        assert result.opportunities_found == 10
        assert result.errors_count == 2
        
        set_bot_instance(None)


class TestGetPositions:
    """Tests for get_positions endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_positions_success(self):
        """Test getting positions successfully."""
        mock_bot = MagicMock()
        
        mock_position = MagicMock()
        mock_position.position_id = "pos1"
        mock_position.status = "open"
        mock_position.asgard = MagicMock()
        mock_position.asgard.asset = MagicMock()
        mock_position.asgard.asset.value = "SOL"
        mock_position.asgard.leverage = Decimal("3.0")
        mock_position.asgard.collateral_usd = Decimal("10000")
        mock_position.asgard.current_value_usd = Decimal("30000")
        mock_position.hyperliquid = MagicMock()
        mock_position.hyperliquid.size_usd = Decimal("30000")
        mock_position.delta = Decimal("100")
        mock_position.delta_ratio = Decimal("0.01")
        mock_position.asgard.current_health_factor = Decimal("1.2")
        mock_position.hyperliquid.margin_fraction = Decimal("0.15")
        mock_position.total_pnl = Decimal("50")
        mock_position.net_funding_pnl = Decimal("30")
        mock_position.created_at = datetime.utcnow()
        
        mock_bot.get_positions.return_value = {"pos1": mock_position}
        set_bot_instance(mock_bot)
        
        with patch('bot.core.internal_api.verify_internal_token'):
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            result = await get_positions(credentials)
        
        assert "pos1" in result
        
        set_bot_instance(None)


class TestGetPositionDetail:
    """Tests for get_position_detail endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_position_detail_success(self):
        """Test getting position detail successfully."""
        mock_bot = MagicMock()
        
        mock_position = MagicMock()
        mock_position.position_id = "pos1"
        mock_position.status = "open"
        mock_position.asgard = MagicMock()
        mock_position.asgard.asset = MagicMock()
        mock_position.asgard.asset.value = "SOL"
        mock_position.asgard.leverage = Decimal("3.0")
        mock_position.asgard.collateral_usd = Decimal("10000")
        mock_position.asgard.current_value_usd = Decimal("30000")
        mock_position.asgard.position_size_usd = Decimal("30000")
        mock_position.asgard.token_b_borrowed = Decimal("20000")
        mock_position.asgard.pnl_usd = Decimal("25")
        mock_position.asgard.position_pda = "pda123"
        mock_position.asgard.token_a_amount = Decimal("100")
        mock_position.asgard.entry_price_token_a = Decimal("150")
        mock_position.asgard.current_token_a_price = Decimal("155")
        mock_position.asgard.current_health_factor = Decimal("1.2")
        mock_position.hyperliquid = MagicMock()
        mock_position.hyperliquid.size_usd = Decimal("30000")
        mock_position.hyperliquid.unrealized_pnl = Decimal("25")
        mock_position.hyperliquid.size_sol = Decimal("100")
        mock_position.hyperliquid.entry_px = Decimal("150")
        mock_position.hyperliquid.mark_px = Decimal("155")
        mock_position.hyperliquid.leverage = Decimal("3.0")
        mock_position.hyperliquid.margin_used = Decimal("5000")
        mock_position.hyperliquid.margin_fraction = Decimal("0.15")
        mock_position.delta = Decimal("100")
        mock_position.delta_ratio = Decimal("0.01")
        mock_position.total_pnl = Decimal("50")
        mock_position.net_funding_pnl = Decimal("30")
        mock_position.created_at = datetime.utcnow()
        mock_position.is_at_risk = False
        
        mock_bot.get_positions.return_value = {"pos1": mock_position}
        set_bot_instance(mock_bot)
        
        with patch('bot.core.internal_api.verify_internal_token'):
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            result = await get_position_detail("pos1", credentials)
        
        assert result.position_id == "pos1"
        
        set_bot_instance(None)
    
    @pytest.mark.asyncio
    async def test_get_position_detail_not_found(self):
        """Test getting non-existent position."""
        mock_bot = MagicMock()
        mock_bot.get_positions.return_value = {}
        set_bot_instance(mock_bot)
        
        with patch('bot.core.internal_api.verify_internal_token'):
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            
            with pytest.raises(HTTPException) as exc_info:
                await get_position_detail("nonexistent", credentials)
            
            assert exc_info.value.status_code == 404
        
        set_bot_instance(None)


class TestGetPauseState:
    """Tests for get_pause_state endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_pause_state_running(self):
        """Test getting pause state when running."""
        mock_bot = MagicMock()
        mock_state = MagicMock()
        mock_state.paused = False
        mock_state.scope = MagicMock()
        mock_state.scope.value = "all"
        mock_state.reason = None
        mock_state.paused_at = None
        mock_state.paused_by = None
        mock_state.active_breakers = []
        mock_bot._pause_controller.get_pause_state.return_value = mock_state
        set_bot_instance(mock_bot)
        
        with patch('bot.core.internal_api.verify_internal_token'):
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            result = await get_pause_state(credentials)
        
        assert result.paused is False
        
        set_bot_instance(None)
    
    @pytest.mark.asyncio
    async def test_get_pause_state_paused(self):
        """Test getting pause state when paused."""
        mock_bot = MagicMock()
        mock_state = MagicMock()
        mock_state.paused = True
        mock_state.scope = MagicMock()
        mock_state.scope.value = "entry"
        mock_state.reason = "Maintenance"
        mock_state.paused_at = datetime.utcnow()
        mock_state.paused_by = "admin"
        mock_state.active_breakers = []
        mock_bot._pause_controller.get_pause_state.return_value = mock_state
        set_bot_instance(mock_bot)
        
        with patch('bot.core.internal_api.verify_internal_token'):
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            result = await get_pause_state(credentials)
        
        assert result.paused is True
        assert result.reason == "Maintenance"
        
        set_bot_instance(None)


class TestPauseBot:
    """Tests for pause_bot endpoint."""
    
    @pytest.mark.asyncio
    async def test_pause_bot_success(self):
        """Test pausing bot successfully."""
        mock_bot = MagicMock()
        mock_bot.pause = AsyncMock(return_value=True)
        set_bot_instance(mock_bot)
        
        with patch('bot.core.internal_api.verify_internal_token'):
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            request = {"api_key": "admin_key", "reason": "Testing", "scope": "all"}
            result = await pause_bot(request, credentials)
        
        assert result["success"] is True
        mock_bot.pause.assert_called_once()
        
        set_bot_instance(None)
    
    @pytest.mark.asyncio
    async def test_pause_bot_with_scope(self):
        """Test pausing bot with specific scope."""
        mock_bot = MagicMock()
        mock_bot.pause = AsyncMock(return_value=True)
        set_bot_instance(mock_bot)
        
        with patch('bot.core.internal_api.verify_internal_token'):
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            request = {"api_key": "admin_key", "reason": "Testing", "scope": "entry"}
            result = await pause_bot(request, credentials)
        
        assert result["success"] is True
        
        set_bot_instance(None)
    
    @pytest.mark.asyncio
    async def test_pause_bot_failure(self):
        """Test pausing bot failure."""
        mock_bot = MagicMock()
        mock_bot.pause = AsyncMock(return_value=False)
        set_bot_instance(mock_bot)
        
        with patch('bot.core.internal_api.verify_internal_token'):
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            request = {"api_key": "admin_key", "reason": "Testing", "scope": "all"}
            result = await pause_bot(request, credentials)
        
        assert result["success"] is False
        
        set_bot_instance(None)


class TestResumeBot:
    """Tests for resume_bot endpoint."""
    
    @pytest.mark.asyncio
    async def test_resume_bot_success(self):
        """Test resuming bot successfully."""
        mock_bot = MagicMock()
        mock_bot.resume = AsyncMock(return_value=True)
        set_bot_instance(mock_bot)
        
        with patch('bot.core.internal_api.verify_internal_token'):
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            request = {"api_key": "admin_key"}
            result = await resume_bot(request, credentials)
        
        assert result["success"] is True
        
        set_bot_instance(None)
    
    @pytest.mark.asyncio
    async def test_resume_bot_failure(self):
        """Test resuming bot failure."""
        mock_bot = MagicMock()
        mock_bot.resume = AsyncMock(return_value=False)
        set_bot_instance(mock_bot)
        
        with patch('bot.core.internal_api.verify_internal_token'):
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            request = {"api_key": "admin_key"}
            result = await resume_bot(request, credentials)
        
        assert result["success"] is False
        
        set_bot_instance(None)


class TestPositionToSummary:
    """Tests for _position_to_summary function."""
    
    def test_position_to_summary(self):
        """Test converting position to summary."""
        mock_position = MagicMock()
        mock_position.position_id = "pos1"
        mock_position.status = "open"
        mock_position.asgard = MagicMock()
        mock_position.asgard.asset = MagicMock()
        mock_position.asgard.asset.value = "SOL"
        mock_position.asgard.leverage = Decimal("3.0")
        mock_position.asgard.collateral_usd = Decimal("10000")
        mock_position.asgard.current_value_usd = Decimal("30000")
        mock_position.hyperliquid = MagicMock()
        mock_position.hyperliquid.size_usd = Decimal("30000")
        mock_position.delta = Decimal("100")
        mock_position.delta_ratio = Decimal("0.01")
        mock_position.asgard.current_health_factor = Decimal("1.2")
        mock_position.hyperliquid.margin_fraction = Decimal("0.15")
        mock_position.total_pnl = Decimal("50")
        mock_position.net_funding_pnl = Decimal("30")
        mock_position.created_at = datetime.utcnow()
        
        result = _position_to_summary(mock_position)
        
        assert isinstance(result, PositionSummary)
        assert result.position_id == "pos1"
        assert result.asset == "SOL"
        assert result.status == "open"


class TestPositionToDetail:
    """Tests for _position_to_detail function."""
    
    def test_position_to_detail(self):
        """Test converting position to detail."""
        mock_position = MagicMock()
        mock_position.position_id = "pos1"
        mock_position.status = "open"
        mock_position.asgard = MagicMock()
        mock_position.asgard.asset = MagicMock()
        mock_position.asgard.asset.value = "SOL"
        mock_position.asgard.leverage = Decimal("3.0")
        mock_position.asgard.collateral_usd = Decimal("10000")
        mock_position.asgard.current_value_usd = Decimal("30000")
        mock_position.asgard.position_size_usd = Decimal("30000")
        mock_position.asgard.token_b_borrowed = Decimal("20000")
        mock_position.asgard.pnl_usd = Decimal("25")
        mock_position.asgard.position_pda = "pda123"
        mock_position.asgard.token_a_amount = Decimal("100")
        mock_position.asgard.entry_price_token_a = Decimal("150")
        mock_position.asgard.current_token_a_price = Decimal("155")
        mock_position.asgard.current_health_factor = Decimal("1.2")
        mock_position.hyperliquid = MagicMock()
        mock_position.hyperliquid.size_usd = Decimal("30000")
        mock_position.hyperliquid.unrealized_pnl = Decimal("25")
        mock_position.hyperliquid.size_sol = Decimal("100")
        mock_position.hyperliquid.entry_px = Decimal("150")
        mock_position.hyperliquid.mark_px = Decimal("155")
        mock_position.hyperliquid.leverage = Decimal("3.0")
        mock_position.hyperliquid.margin_used = Decimal("5000")
        mock_position.hyperliquid.margin_fraction = Decimal("0.15")
        mock_position.delta = Decimal("100")
        mock_position.delta_ratio = Decimal("0.01")
        mock_position.total_pnl = Decimal("50")
        mock_position.net_funding_pnl = Decimal("30")
        mock_position.created_at = datetime.utcnow()
        mock_position.is_at_risk = False
        
        result = _position_to_detail(mock_position)
        
        assert isinstance(result, PositionDetail)
        assert result.position_id == "pos1"
        assert "sizing" in result.model_dump()
        assert "asgard" in result.model_dump()
        assert "hyperliquid" in result.model_dump()
        assert "pnl" in result.model_dump()
        assert "risk" in result.model_dump()
