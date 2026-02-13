"""
Test settings and configuration loading.
"""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shared.config.settings import (
    Settings,
    get_settings,
    reload_settings,
    load_risk_config,
    get_risk_limits,
    get_funding_config,
    _settings,
)


@pytest.fixture
def mock_env():
    """Provide mock environment variables."""
    return {
        "ASGARD_API_KEY": "test_key",
        "SOLANA_RPC_URL": "https://test.solana.com",
        "ARBITRUM_RPC_URL": "https://test.arbitrum.com",
        "PRIVY_APP_ID": "test_app_id",
        "PRIVY_APP_SECRET": "test_secret",
    }


def test_settings_validation(mock_env):
    """Test that settings load and validate correctly."""
    # Clear cached settings before patching environment
    import shared.config.settings as settings_module
    settings_module._settings = None
    
    with patch.dict(os.environ, mock_env, clear=True):
        settings = reload_settings()
        
        assert settings.asgard_api_key == "test_key"
        assert settings.solana_rpc_url == "https://test.solana.com"
        assert settings.arbitrum_rpc_url == "https://test.arbitrum.com"
        assert settings.privy_app_id == "test_app_id"
        assert settings.privy_app_secret == "test_secret"
        assert settings.log_level == "INFO"  # default


def test_settings_validation_missing():
    """Test settings validation catches missing secrets."""
    import shared.config.settings as settings_module
    settings_module._settings = None
    
    def mock_load_secret(filename):
        return None  # All secrets missing
    
    with patch('shared.config.settings.load_secret', side_effect=mock_load_secret):
        with patch('shared.config.settings.SECRETS_DIR', settings_module.BASE_DIR / "nonexistent"):
            settings = Settings()
            missing = settings.validate()
            
            # Should require these critical files
            assert "asgard_api_key.txt" in missing
            assert "privy_app_id.txt" in missing
            assert "privy_app_secret.txt" in missing
            assert "solana_rpc_url.txt" in missing
            assert "arbitrum_rpc_url.txt" in missing
            assert "privy_auth.pem" in missing


class TestSettingsPrivy:
    """Test settings with Privy configuration."""
    
    @patch('shared.config.settings.load_secret')
    def test_check_required_secrets_privy(self, mock_load_secret):
        """Test that Privy secrets are checked."""
        # Mock empty secrets
        mock_load_secret.return_value = None
        
        settings = Settings()
        missing = settings.validate()
        
        # Should require Privy fields
        assert "privy_app_id.txt" in missing
        assert "privy_app_secret.txt" in missing
    
    @patch('shared.config.settings.load_secret')
    @patch('pathlib.Path.exists')
    def test_check_required_secrets_no_auth_key(self, mock_exists, mock_load_secret):
        """Test missing auth key file is detected."""
        mock_exists.return_value = False
        mock_load_secret.return_value = "exists"
        
        settings = Settings()
        missing = settings.validate()
        
        assert "privy_auth.pem" in missing
    
    @patch('shared.config.settings.load_secret')
    @patch('pathlib.Path.exists')
    def test_all_secrets_present(self, mock_exists, mock_load_secret):
        """Test no missing secrets when all present."""
        mock_exists.return_value = True
        mock_load_secret.return_value = "present"
        
        settings = Settings()
        missing = settings.validate()
        
        assert len(missing) == 0


def test_risk_config_loading():
    """Test risk configuration YAML loading."""
    config = load_risk_config()
    
    assert "risk_limits" in config
    assert "fee_market" in config
    assert "funding" in config
    assert "monitoring" in config


def test_risk_limits():
    """Test risk limits are accessible."""
    limits = get_risk_limits()
    
    assert "default_leverage" in limits
    assert "max_leverage" in limits
    assert "min_position_usd" in limits
    
    assert limits["default_leverage"] == 3.0
    assert limits["max_leverage"] == 4.0
    assert limits["min_position_usd"] == 100


def test_funding_config():
    """Test funding rate configuration."""
    funding_config = get_funding_config()
    
    assert "lookback_hours" in funding_config
    assert "max_volatility" in funding_config
    
    assert funding_config["lookback_hours"] == 168  # 1 week
    assert funding_config["max_volatility"] == 0.50  # 50%
