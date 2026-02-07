"""
Tests for dashboard control API (pause, resume, emergency stop).
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from fastapi import HTTPException


class TestPauseBot:
    """Tests for POST /pause endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.control.require_bot_bridge')
    @patch('src.dashboard.api.control.get_dashboard_settings')
    async def test_pause_success(self, mock_get_settings, mock_require_bridge):
        """Test pausing bot successfully."""
        from src.dashboard.api.control import pause_bot, PauseRequest
        
        # Mock bot bridge
        mock_bridge = AsyncMock()
        mock_bridge.pause.return_value = True
        mock_require_bridge.return_value = mock_bridge
        
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.bot_admin_key = "test_key"
        mock_get_settings.return_value = mock_settings
        
        # Mock user
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        request = PauseRequest(reason="Maintenance", scope="all")
        
        result = await pause_bot(request, user=mock_user)
        
        assert result.success is True
        assert "paused" in result.message.lower()
        mock_bridge.pause.assert_called_once_with(
            api_key="test_key",
            reason="Maintenance (by test_user)",
            scope="all"
        )
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.control.require_bot_bridge')
    @patch('src.dashboard.api.control.get_dashboard_settings')
    async def test_pause_with_scope(self, mock_get_settings, mock_require_bridge):
        """Test pausing with different scopes."""
        from src.dashboard.api.control import pause_bot, PauseRequest
        
        mock_bridge = AsyncMock()
        mock_bridge.pause.return_value = True
        mock_require_bridge.return_value = mock_bridge
        
        mock_settings = MagicMock()
        mock_settings.bot_admin_key = "test_key"
        mock_get_settings.return_value = mock_settings
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        # Test entry scope
        request = PauseRequest(reason="Testing", scope="entry")
        result = await pause_bot(request, user=mock_user)
        
        mock_bridge.pause.assert_called_with(
            api_key="test_key",
            reason="Testing (by test_user)",
            scope="entry"
        )
        
        # Test asgard scope
        request = PauseRequest(reason="Testing", scope="asgard")
        result = await pause_bot(request, user=mock_user)
        
        mock_bridge.pause.assert_called_with(
            api_key="test_key",
            reason="Testing (by test_user)",
            scope="asgard"
        )
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.control.require_bot_bridge')
    @patch('src.dashboard.api.control.get_dashboard_settings')
    async def test_pause_failure(self, mock_get_settings, mock_require_bridge):
        """Test handling pause failure."""
        from src.dashboard.api.control import pause_bot, PauseRequest
        
        mock_bridge = AsyncMock()
        mock_bridge.pause.return_value = False
        mock_require_bridge.return_value = mock_bridge
        
        mock_settings = MagicMock()
        mock_settings.bot_admin_key = "test_key"
        mock_get_settings.return_value = mock_settings
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        request = PauseRequest(reason="Test", scope="all")
        result = await pause_bot(request, user=mock_user)
        
        assert result.success is False
        assert "failed" in result.message.lower()
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.control.require_bot_bridge')
    @patch('src.dashboard.api.control.get_dashboard_settings')
    async def test_pause_exception(self, mock_get_settings, mock_require_bridge):
        """Test handling exception during pause."""
        from src.dashboard.api.control import pause_bot, PauseRequest
        
        mock_bridge = AsyncMock()
        mock_bridge.pause.side_effect = Exception("Connection error")
        mock_require_bridge.return_value = mock_bridge
        
        mock_settings = MagicMock()
        mock_settings.bot_admin_key = "test_key"
        mock_get_settings.return_value = mock_settings
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        request = PauseRequest(reason="Test", scope="all")
        
        with pytest.raises(HTTPException) as exc_info:
            await pause_bot(request, user=mock_user)
        
        assert exc_info.value.status_code == 503


class TestResumeBot:
    """Tests for POST /resume endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.control.require_bot_bridge')
    @patch('src.dashboard.api.control.get_dashboard_settings')
    async def test_resume_success(self, mock_get_settings, mock_require_bridge):
        """Test resuming bot successfully."""
        from src.dashboard.api.control import resume_bot, ResumeRequest
        
        mock_bridge = AsyncMock()
        mock_bridge.resume.return_value = True
        mock_require_bridge.return_value = mock_bridge
        
        mock_settings = MagicMock()
        mock_settings.bot_admin_key = "test_key"
        mock_get_settings.return_value = mock_settings
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        request = ResumeRequest()
        result = await resume_bot(request, user=mock_user)
        
        assert result.success is True
        assert "resumed" in result.message.lower()
        mock_bridge.resume.assert_called_once_with(api_key="test_key")
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.control.require_bot_bridge')
    @patch('src.dashboard.api.control.get_dashboard_settings')
    async def test_resume_failure(self, mock_get_settings, mock_require_bridge):
        """Test handling resume failure."""
        from src.dashboard.api.control import resume_bot, ResumeRequest
        
        mock_bridge = AsyncMock()
        mock_bridge.resume.return_value = False
        mock_require_bridge.return_value = mock_bridge
        
        mock_settings = MagicMock()
        mock_settings.bot_admin_key = "test_key"
        mock_get_settings.return_value = mock_settings
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        request = ResumeRequest()
        result = await resume_bot(request, user=mock_user)
        
        assert result.success is False
        assert "failed" in result.message.lower()
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.control.require_bot_bridge')
    @patch('src.dashboard.api.control.get_dashboard_settings')
    async def test_resume_exception(self, mock_get_settings, mock_require_bridge):
        """Test handling exception during resume."""
        from src.dashboard.api.control import resume_bot, ResumeRequest
        
        mock_bridge = AsyncMock()
        mock_bridge.resume.side_effect = Exception("Connection error")
        mock_require_bridge.return_value = mock_bridge
        
        mock_settings = MagicMock()
        mock_settings.bot_admin_key = "test_key"
        mock_get_settings.return_value = mock_settings
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        request = ResumeRequest()
        
        with pytest.raises(HTTPException) as exc_info:
            await resume_bot(request, user=mock_user)
        
        assert exc_info.value.status_code == 503


class TestEmergencyStop:
    """Tests for POST /emergency-stop endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.control.require_bot_bridge')
    @patch('src.dashboard.api.control.get_dashboard_settings')
    async def test_emergency_stop_success(self, mock_get_settings, mock_require_bridge):
        """Test emergency stop successfully."""
        from src.dashboard.api.control import emergency_stop
        
        mock_bridge = AsyncMock()
        mock_bridge.pause.return_value = True
        mock_require_bridge.return_value = mock_bridge
        
        mock_settings = MagicMock()
        mock_settings.bot_admin_key = "test_key"
        mock_get_settings.return_value = mock_settings
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        result = await emergency_stop(user=mock_user)
        
        assert result.success is True
        assert "emergency" in result.message.lower()
        mock_bridge.pause.assert_called_once_with(
            api_key="test_key",
            reason="EMERGENCY STOP triggered by test_user",
            scope="all"
        )
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.control.require_bot_bridge')
    @patch('src.dashboard.api.control.get_dashboard_settings')
    async def test_emergency_stop_failure(self, mock_get_settings, mock_require_bridge):
        """Test handling emergency stop failure."""
        from src.dashboard.api.control import emergency_stop
        
        mock_bridge = AsyncMock()
        mock_bridge.pause.return_value = False
        mock_require_bridge.return_value = mock_bridge
        
        mock_settings = MagicMock()
        mock_settings.bot_admin_key = "test_key"
        mock_get_settings.return_value = mock_settings
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        result = await emergency_stop(user=mock_user)
        
        assert result.success is False
        assert "failed" in result.message.lower()
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.control.require_bot_bridge')
    @patch('src.dashboard.api.control.get_dashboard_settings')
    async def test_emergency_stop_exception(self, mock_get_settings, mock_require_bridge):
        """Test handling exception during emergency stop."""
        from src.dashboard.api.control import emergency_stop
        
        mock_bridge = AsyncMock()
        mock_bridge.pause.side_effect = Exception("Connection error")
        mock_require_bridge.return_value = mock_bridge
        
        mock_settings = MagicMock()
        mock_settings.bot_admin_key = "test_key"
        mock_get_settings.return_value = mock_settings
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        with pytest.raises(HTTPException) as exc_info:
            await emergency_stop(user=mock_user)
        
        assert exc_info.value.status_code == 503


class TestPauseRequest:
    """Tests for PauseRequest model."""
    
    def test_default_values(self):
        """Test default values for PauseRequest."""
        from src.dashboard.api.control import PauseRequest
        
        request = PauseRequest(reason="Test")
        
        assert request.reason == "Test"
        assert request.scope == "all"
    
    def test_custom_scope(self):
        """Test PauseRequest with custom scope."""
        from src.dashboard.api.control import PauseRequest
        
        request = PauseRequest(reason="Test", scope="entry")
        
        assert request.scope == "entry"
    
    def test_valid_scopes(self):
        """Test all valid pause scopes."""
        from src.dashboard.api.control import PauseRequest
        
        scopes = ["all", "entry", "exit", "asgard", "hyperliquid"]
        
        for scope in scopes:
            request = PauseRequest(reason="Test", scope=scope)
            assert request.scope == scope


class TestResumeRequest:
    """Tests for ResumeRequest model."""
    
    def test_creation(self):
        """Test creating ResumeRequest."""
        from src.dashboard.api.control import ResumeRequest
        
        request = ResumeRequest()
        
        # ResumeRequest has no fields
        assert request is not None
