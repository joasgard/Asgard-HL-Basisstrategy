"""
Application settings with Pydantic validation.

Supports loading secrets from multiple sources (in order of priority):
1. Environment variables (highest priority)
2. Secret files in secrets/ directory
3. .env file (lowest priority)

This allows you to share the repository without leaking credentials by:
- Keeping sensitive data in secrets/ directory (git-ignored)
- Committing only .example files as templates
"""
import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory
BASE_DIR = Path(__file__).parent.parent.parent
SECRETS_DIR = BASE_DIR / "secrets"


def load_secret_from_file(filename: str) -> Optional[str]:
    """
    Load a secret from a file in the secrets directory.
    
    Args:
        filename: Name of the file in secrets/ directory
        
    Returns:
        The secret value (stripped of whitespace), or None if file doesn't exist
    """
    secret_path = SECRETS_DIR / filename
    if secret_path.exists():
        try:
            with open(secret_path, "r") as f:
                return f.read().strip()
        except (IOError, OSError):
            return None
    return None


def get_secret(env_var: str, secret_file: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a secret from environment variable or file.
    
    Priority:
    1. Environment variable
    2. Secret file
    3. Default value
    
    Args:
        env_var: Name of the environment variable
        secret_file: Name of the file in secrets/ directory
        default: Default value if not found elsewhere
        
    Returns:
        The secret value or default
    """
    # First check environment variable
    env_value = os.getenv(env_var)
    if env_value:
        return env_value
    
    # Then check secret file
    file_value = load_secret_from_file(secret_file)
    if file_value:
        return file_value
    
    return default


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and secret files.
    
    Secrets can be provided via:
    1. Environment variables (highest priority)
    2. Files in secrets/ directory
    3. .env file (lowest priority)
    
    Example:
        # Using environment variable
        export ASGARD_API_KEY=your_key
        
        # Using secret file
        echo "your_key" > secrets/asgard_api_key.txt
        
        # Using .env file
        echo "ASGARD_API_KEY=your_key" >> .env
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    # Environment
    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    paper_trading: bool = Field(default=True, alias="PAPER_TRADING")
    
    # Asgard (Solana) - loaded from env or secrets file
    asgard_api_key: str = Field(
        default_factory=lambda: get_secret("ASGARD_API_KEY", "asgard_api_key.txt", ""),
        alias="ASGARD_API_KEY"
    )
    solana_rpc_url: str = Field(
        default_factory=lambda: get_secret("SOLANA_RPC_URL", "solana_rpc_url.txt", ""),
        alias="SOLANA_RPC_URL"
    )
    solana_wallet_address: str = Field(
        default_factory=lambda: get_secret("SOLANA_WALLET_ADDRESS", "solana_wallet_address.txt", ""),
        alias="SOLANA_WALLET_ADDRESS"
    )
    
    # Hyperliquid (Arbitrum) - loaded from env or secrets file
    hyperliquid_wallet_address: str = Field(
        default_factory=lambda: get_secret("HYPERLIQUID_WALLET_ADDRESS", "hyperliquid_wallet_address.txt", ""),
        alias="HYPERLIQUID_WALLET_ADDRESS"
    )
    # Privy Configuration
    privy_app_id: str = Field(
        default_factory=lambda: get_secret("PRIVY_APP_ID", "privy_app_id.txt", ""),
        alias="PRIVY_APP_ID"
    )
    privy_app_secret: str = Field(
        default_factory=lambda: get_secret("PRIVY_APP_SECRET", "privy_app_secret.txt", ""),
        alias="PRIVY_APP_SECRET"
    )
    privy_auth_key_path: str = Field(
        default="privy_auth.pem",
        alias="PRIVY_AUTH_KEY_PATH"
    )
    wallet_address: str = Field(
        default_factory=lambda: get_secret("WALLET_ADDRESS", "wallet_address.txt", ""),
        alias="WALLET_ADDRESS"
    )
    arbitrum_rpc_url: Optional[str] = Field(
        default_factory=lambda: get_secret("ARBITRUM_RPC_URL", "arbitrum_rpc_url.txt"),
        alias="ARBITRUM_RPC_URL"
    )
    
    # Admin - loaded from env or secrets file
    admin_api_key: Optional[str] = Field(
        default_factory=lambda: get_secret("ADMIN_API_KEY", "admin_api_key.txt"),
        alias="ADMIN_API_KEY"
    )
    
    # Optional: Sentry - loaded from env or secrets file
    sentry_dsn: Optional[str] = Field(
        default_factory=lambda: get_secret("SENTRY_DSN", "sentry_dsn.txt"),
        alias="SENTRY_DSN"
    )
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v.lower() not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v.lower()
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.upper()
    
    @property
    def is_production(self) -> bool:
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment == "development"
    
    def check_required_secrets(self) -> list[str]:
        """
        Check if all required secrets are configured.
        
        Returns:
            List of missing secret names (empty if all present)
        """
        missing = []
        
        if not self.asgard_api_key:
            missing.append("ASGARD_API_KEY (asgard_api_key.txt or env var)")
        if not self.solana_rpc_url:
            missing.append("SOLANA_RPC_URL (solana_rpc_url.txt or env var)")
        if not self.hyperliquid_wallet_address:
            missing.append("HYPERLIQUID_WALLET_ADDRESS (hyperliquid_wallet_address.txt or env var)")
        
        # Privy requirements
        if not self.privy_app_id:
            missing.append("PRIVY_APP_ID (privy_app_id.txt or env var)")
        if not self.privy_app_secret:
            missing.append("PRIVY_APP_SECRET (privy_app_secret.txt or env var)")
        if not self.wallet_address:
            missing.append("WALLET_ADDRESS (wallet_address.txt or env var)")
        
        # Check auth key file exists
        auth_key_path = Path(self.privy_auth_key_path)
        if not auth_key_path.exists():
            missing.append(f"PRIVY_AUTH_KEY ({self.privy_auth_key_path} not found)")
        
        return missing


# Global settings instance (lazy-loaded)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment."""
    global _settings
    _settings = Settings()
    return _settings


# Risk configuration loaded from YAML
_risk_config: Optional[dict] = None


def load_risk_config() -> dict:
    """Load risk configuration from YAML file."""
    global _risk_config
    if _risk_config is None:
        risk_yaml_path = BASE_DIR / "src" / "config" / "risk.yaml"
        if not risk_yaml_path.exists():
            raise FileNotFoundError(f"Risk config not found: {risk_yaml_path}")
        
        with open(risk_yaml_path, "r") as f:
            _risk_config = yaml.safe_load(f)
    
    return _risk_config


def get_risk_limits() -> dict:
    """Get risk limits section from config."""
    return load_risk_config().get("risk_limits", {})


def get_funding_config() -> dict:
    """Get funding rate config section."""
    return load_risk_config().get("funding", {})
