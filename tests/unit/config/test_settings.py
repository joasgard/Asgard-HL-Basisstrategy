"""
Test settings and configuration loading.
"""
import os
from unittest.mock import patch

import pytest

from src.config.settings import (
    get_settings,
    reload_settings,
    load_risk_config,
    get_risk_limits,
    get_fee_market_config,
    get_funding_config,
    _settings,
)


@pytest.fixture
def mock_env():
    """Provide mock environment variables."""
    return {
        "ASGARD_API_KEY": "test_key",
        "SOLANA_RPC_URL": "https://test.solana.com",
        "SOLANA_PRIVATE_KEY": "test_private_key",
        "HYPERLIQUID_WALLET_ADDRESS": "0x123",
        "HYPERLIQUID_PRIVATE_KEY": "0xabc",
    }


def test_settings_validation(mock_env):
    """Test that settings load and validate correctly."""
    # Clear cached settings before patching environment
    import src.config.settings as settings_module
    settings_module._settings = None
    
    with patch.dict(os.environ, mock_env, clear=True):
        settings = reload_settings()
        
        assert settings.asgard_api_key == "test_key"
        assert settings.solana_rpc_url == "https://test.solana.com"
        assert settings.hyperliquid_wallet_address == "0x123"
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


def test_fee_market_config():
    """Test fee market configuration."""
    fee_config = get_fee_market_config()
    
    assert "max_cup_micro_lamports" in fee_config
    assert "max_fee_sol" in fee_config


def test_funding_config():
    """Test funding rate configuration."""
    funding_config = get_funding_config()
    
    assert "lookback_hours" in funding_config
    assert "max_volatility" in funding_config
    
    assert funding_config["lookback_hours"] == 168  # 1 week
    assert funding_config["max_volatility"] == 0.50  # 50%
