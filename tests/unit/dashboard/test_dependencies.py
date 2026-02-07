"""
Tests for dashboard dependencies.
"""
import pytest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from src.dashboard.dependencies import (
    set_bot_bridge, get_bot_bridge, require_bot_bridge,
    _bot_bridge
)


class TestBotBridgeDependencies:
    """Tests for bot bridge dependencies."""
    
    def test_set_bot_bridge(self):
        """Test setting bot bridge."""
        mock_bridge = MagicMock()
        
        set_bot_bridge(mock_bridge)
        
        assert get_bot_bridge() is mock_bridge
        
        # Reset
        set_bot_bridge(None)
    
    def test_get_bot_bridge_initial(self):
        """Test getting bot bridge when not set."""
        set_bot_bridge(None)
        
        result = get_bot_bridge()
        
        assert result is None
    
    def test_require_bot_bridge_success(self):
        """Test requiring bot bridge when set."""
        mock_bridge = MagicMock()
        set_bot_bridge(mock_bridge)
        
        result = require_bot_bridge()
        
        assert result is mock_bridge
        
        set_bot_bridge(None)
    
    def test_require_bot_bridge_not_set(self):
        """Test requiring bot bridge when not set raises 503."""
        set_bot_bridge(None)
        
        with pytest.raises(HTTPException) as exc_info:
            require_bot_bridge()
        
        assert exc_info.value.status_code == 503
        assert "Dashboard not initialized" in exc_info.value.detail
