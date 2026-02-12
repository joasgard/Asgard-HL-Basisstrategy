"""
Tests for dashboard settings API.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import json

from fastapi import HTTPException


class TestGetSettings:
    """Tests for GET /settings endpoint."""
    
    @pytest.mark.asyncio
    @patch('backend.dashboard.api.settings.load_settings')
    @patch('backend.dashboard.api.settings.get_db')
    async def test_get_settings_returns_defaults(self, mock_get_db, mock_load_settings):
        """Test that get_settings returns default settings when none saved."""
        from backend.dashboard.api.settings import get_settings
        from backend.dashboard.api.settings import StrategySettings
        
        # Mock default settings
        mock_settings = StrategySettings()
        mock_load_settings.return_value = mock_settings
        
        # Mock db
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        result = await get_settings(db=mock_db)
        
        assert result.success is True
        assert result.settings is not None
        assert result.settings.default_leverage == 3.0
    
    @pytest.mark.asyncio
    @patch('backend.dashboard.api.settings.load_settings')
    @patch('backend.dashboard.api.settings.get_db')
    async def test_get_settings_returns_saved(self, mock_get_db, mock_load_settings):
        """Test that get_settings returns saved settings."""
        from backend.dashboard.api.settings import get_settings, StrategySettings
        
        # Mock saved settings
        mock_settings = StrategySettings(
            default_leverage=4.0,
            max_position_size=100000
        )
        mock_load_settings.return_value = mock_settings
        
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        result = await get_settings(db=mock_db)
        
        assert result.success is True
        assert result.settings.default_leverage == 4.0
        assert result.settings.max_position_size == 100000


class TestSaveSettings:
    """Tests for POST /settings endpoint."""
    
    @pytest.mark.asyncio
    @patch('backend.dashboard.api.settings.store_settings')
    @patch('backend.dashboard.api.settings.get_db')
    async def test_save_settings_success(self, mock_get_db, mock_store_settings):
        """Test saving settings successfully."""
        from backend.dashboard.api.settings import save_settings, StrategySettings, SettingsResponse
        
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_get_db.return_value = mock_db

        mock_user = MagicMock()
        mock_user.user_id = "test_user"

        settings = StrategySettings(
            default_leverage=4.0,
            max_position_size=100000
        )

        result = await save_settings(settings, user=mock_user, db=mock_db)

        assert result.success is True
        mock_store_settings.assert_called_once()
        mock_db.execute.assert_called_once()  # Audit log
    
    @pytest.mark.asyncio
    @patch('backend.dashboard.api.settings.store_settings')
    @patch('backend.dashboard.api.settings.get_db')
    async def test_save_settings_error(self, mock_get_db, mock_store_settings):
        """Test handling error when saving settings."""
        from backend.dashboard.api.settings import save_settings, StrategySettings
        
        mock_store_settings.side_effect = Exception("Database error")
        
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        settings = StrategySettings(default_leverage=3.0)
        
        with pytest.raises(HTTPException) as exc_info:
            await save_settings(settings, user=mock_user, db=mock_db)
        
        assert exc_info.value.status_code == 500


class TestResetSettings:
    """Tests for POST /settings/reset endpoint."""
    
    @pytest.mark.asyncio
    @patch('backend.dashboard.api.settings.store_settings')
    @patch('backend.dashboard.api.settings.get_db')
    async def test_reset_settings_success(self, mock_get_db, mock_store_settings):
        """Test resetting settings to defaults."""
        from backend.dashboard.api.settings import reset_settings, StrategySettings
        
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_get_db.return_value = mock_db

        mock_user = MagicMock()
        mock_user.user_id = "test_user"

        result = await reset_settings(user=mock_user, db=mock_db)
        
        assert result.success is True
        assert result.settings is not None
        # Should be default values
        assert result.settings.default_leverage == 3.0
        mock_store_settings.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('backend.dashboard.api.settings.store_settings')
    @patch('backend.dashboard.api.settings.get_db')
    async def test_reset_settings_error(self, mock_get_db, mock_store_settings):
        """Test handling error when resetting settings."""
        from backend.dashboard.api.settings import reset_settings
        
        mock_store_settings.side_effect = Exception("Database error")
        
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        with pytest.raises(HTTPException) as exc_info:
            await reset_settings(user=mock_user, db=mock_db)
        
        assert exc_info.value.status_code == 500


class TestStrategySettings:
    """Tests for StrategySettings model."""
    
    def test_default_values(self):
        """Test default values for StrategySettings."""
        from backend.dashboard.api.settings import StrategySettings
        
        settings = StrategySettings()
        
        assert settings.default_leverage == 3.0
        assert settings.max_position_size == 50000
        assert settings.min_position_size == 100
        assert settings.max_positions_per_asset == 1
        assert settings.min_opportunity_apy == 1.0
        assert settings.max_funding_volatility == 50.0
        assert settings.price_deviation_threshold == 0.5
        assert settings.delta_drift_threshold == 0.5
        assert settings.enable_auto_exit is True
        assert settings.enable_circuit_breakers is True
    
    def test_custom_values(self):
        """Test creating StrategySettings with custom values."""
        from backend.dashboard.api.settings import StrategySettings
        
        settings = StrategySettings(
            default_leverage=4.0,
            max_position_size=100000,
            enable_auto_exit=False
        )
        
        assert settings.default_leverage == 4.0
        assert settings.max_position_size == 100000
        assert settings.enable_auto_exit is False
        # Other values should be defaults
        assert settings.min_position_size == 100
    
    def test_leverage_validation(self):
        """Test leverage validation constraints (1.1x - 4x)."""
        from backend.dashboard.api.settings import StrategySettings
        from pydantic import ValidationError
        
        # Too low (below 1.1)
        with pytest.raises(ValidationError):
            StrategySettings(default_leverage=1.0)
        
        # Too high (above 4)
        with pytest.raises(ValidationError):
            StrategySettings(default_leverage=5.0)
        
        # Valid boundary values (new range: 1.1x - 4x)
        settings_min = StrategySettings(default_leverage=1.1)
        assert settings_min.default_leverage == 1.1
        
        settings_max = StrategySettings(default_leverage=4.0)
        assert settings_max.default_leverage == 4.0
        
        # Middle value that was previously invalid
        settings_mid = StrategySettings(default_leverage=1.5)
        assert settings_mid.default_leverage == 1.5
    
    def test_max_position_size_validation(self):
        """Test max_position_size validation (min $100)."""
        from backend.dashboard.api.settings import StrategySettings
        from pydantic import ValidationError
        
        # Too low (below $100 minimum)
        with pytest.raises(ValidationError):
            StrategySettings(max_position_size=50)
        
        # Valid at new minimum
        settings = StrategySettings(max_position_size=100)
        assert settings.max_position_size == 100
        
        # Valid at higher value
        settings2 = StrategySettings(max_position_size=1000)
        assert settings2.max_position_size == 1000


class TestSettingsResponse:
    """Tests for SettingsResponse model."""
    
    def test_response_creation(self):
        """Test creating SettingsResponse."""
        from backend.dashboard.api.settings import SettingsResponse, StrategySettings
        
        settings = StrategySettings()
        response = SettingsResponse(
            success=True,
            message="Settings saved",
            settings=settings
        )
        
        assert response.success is True
        assert response.message == "Settings saved"
        assert response.settings is not None
    
    def test_response_without_settings(self):
        """Test creating SettingsResponse without settings."""
        from backend.dashboard.api.settings import SettingsResponse
        
        response = SettingsResponse(
            success=False,
            message="Error occurred"
        )
        
        assert response.success is False
        assert response.settings is None
