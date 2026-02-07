"""
Test settings and configuration loading.
"""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config.settings import (
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
        "SOLANA_WALLET_ADDRESS": "test_solana_address",
        "HYPERLIQUID_WALLET_ADDRESS": "0x123",
        "PRIVY_APP_ID": "test_app_id",
        "PRIVY_APP_SECRET": "test_secret",
        "WALLET_ADDRESS": "0xabc",
    }


def test_settings_validation(mock_env):
    """Test that settings load and validate correctly."""
    # Clear cached settings before patching environment
    import src.config.settings as settings_module
    settings_module._settings = None
    
    with patch.dict(os.environ, mock_env, clear=True):
        with patch.object(Path, 'exists', return_value=True):
            settings = reload_settings()
            
            assert settings.asgard_api_key == "test_key"
            assert settings.solana_rpc_url == "https://test.solana.com"
            assert settings.hyperliquid_wallet_address == "0x123"
            assert settings.privy_app_id == "test_app_id"
            assert settings.privy_app_secret == "test_secret"
            assert settings.wallet_address == "0xabc"
            assert settings.paper_trading is True  # default
            assert settings.environment == "development"  # default


def test_environment_validation(mock_env):
    """Test environment string validation."""
    mock_env["ENVIRONMENT"] = "invalid"
    
    # Clear cached settings
    import src.config.settings as settings_module
    settings_module._settings = None
    
    with patch.dict(os.environ, mock_env, clear=True):
        with pytest.raises(ValueError, match="environment must be one of"):
            reload_settings()


def test_log_level_validation(mock_env):
    """Test log level validation."""
    mock_env["LOG_LEVEL"] = "INVALID"
    
    # Clear cached settings
    import src.config.settings as settings_module
    settings_module._settings = None
    
    with patch.dict(os.environ, mock_env, clear=True):
        with pytest.raises(ValueError, match="log_level must be one of"):
            reload_settings()


class TestSettingsPrivy:
    """Test settings with Privy configuration."""
    
    @patch('src.config.settings.get_secret')
    @patch('pathlib.Path.exists')
    def test_check_required_secrets_privy(self, mock_exists, mock_get_secret):
        """Test that Privy secrets are checked."""
        # Mock auth key file exists
        mock_exists.return_value = True
        
        # Mock empty secrets
        mock_get_secret.return_value = ""
        
        settings = Settings()
        missing = settings.check_required_secrets()
        
        # Should require Privy fields
        assert any("PRIVY_APP_ID" in m for m in missing)
        assert any("PRIVY_APP_SECRET" in m for m in missing)
        assert any("WALLET_ADDRESS" in m for m in missing)
    
    @patch('src.config.settings.get_secret')
    @patch('pathlib.Path.exists')
    def test_check_required_secrets_no_auth_key(self, mock_exists, mock_get_secret):
        """Test missing auth key file is detected."""
        mock_exists.return_value = False
        mock_get_secret.return_value = "exists"
        
        settings = Settings()
        missing = settings.check_required_secrets()
        
        assert any("PRIVY_AUTH_KEY" in m for m in missing)
    
    @patch('src.config.settings.get_secret')
    @patch('pathlib.Path.exists')
    def test_all_secrets_present(self, mock_exists, mock_get_secret):
        """Test no missing secrets when all present."""
        mock_exists.return_value = True
        mock_get_secret.return_value = "present"
        
        settings = Settings()
        missing = settings.check_required_secrets()
        
        # Should not have old private key fields
        assert not any("HYPERLIQUID_PRIVATE_KEY" in m for m in missing)
        assert not any("SOLANA_PRIVATE_KEY" in m for m in missing)


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
    assert limits["min_position_usd"] == 1000


def test_funding_config():
    """Test funding rate configuration."""
    funding_config = get_funding_config()
    
    assert "lookback_hours" in funding_config
    assert "max_volatility" in funding_config
    
    assert funding_config["lookback_hours"] == 168  # 1 week
    assert funding_config["max_volatility"] == 0.50  # 50%
