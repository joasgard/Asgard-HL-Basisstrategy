"""
Minimal application settings for Asgard Basis.

Required secrets (in secrets/ directory):
- asgard_api_key.txt
- privy_app_id.txt
- privy_app_secret.txt
- solana_rpc_url.txt
- arbitrum_rpc_url.txt
- privy_auth.pem (key file)
"""
import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).parent.parent.parent
SECRETS_DIR = BASE_DIR / "secrets"


def load_secret(filename: str) -> Optional[str]:
    """Load a secret from file."""
    secret_path = SECRETS_DIR / filename
    if secret_path.exists():
        try:
            with open(secret_path, "r") as f:
                return f.read().strip()
        except (IOError, OSError):
            return None
    return None


def get_secret(env_var: str, secret_file: str) -> Optional[str]:
    """Get secret from env var or file."""
    return os.getenv(env_var) or load_secret(secret_file)


class Settings(BaseSettings):
    """Minimal settings - only critical configuration."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    
    # Asgard (Solana)
    asgard_api_key: str = Field(
        default_factory=lambda: get_secret("ASGARD_API_KEY", "asgard_api_key.txt") or "",
        alias="ASGARD_API_KEY"
    )
    solana_rpc_url: str = Field(
        default_factory=lambda: get_secret("SOLANA_RPC_URL", "solana_rpc_url.txt") or "",
        alias="SOLANA_RPC_URL"
    )
    
    # Hyperliquid (Arbitrum)
    arbitrum_rpc_url: str = Field(
        default_factory=lambda: get_secret("ARBITRUM_RPC_URL", "arbitrum_rpc_url.txt") or "",
        alias="ARBITRUM_RPC_URL"
    )
    
    # Privy (REQUIRED for signing)
    privy_app_id: str = Field(
        default_factory=lambda: get_secret("PRIVY_APP_ID", "privy_app_id.txt") or "",
        alias="PRIVY_APP_ID"
    )
    privy_app_secret: str = Field(
        default_factory=lambda: get_secret("PRIVY_APP_SECRET", "privy_app_secret.txt") or "",
        alias="PRIVY_APP_SECRET"
    )
    
    # Privy auth key path (for signing)
    privy_auth_key_path: str = Field(
        default_factory=lambda: str(SECRETS_DIR / "privy_auth.pem"),
        alias="PRIVY_AUTH_KEY_PATH"
    )

    # Admin API key (for bot control)
    admin_api_key: str = Field(
        default_factory=lambda: get_secret("ADMIN_API_KEY", "admin_api_key.txt") or "",
        alias="ADMIN_API_KEY"
    )

    # Hyperliquid bridge contract on Arbitrum
    hl_bridge_contract: Optional[str] = Field(
        default="0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7",
        alias="HL_BRIDGE_CONTRACT"
    )

    # Optional: Default wallet addresses (used if not in database)
    solana_wallet_address: Optional[str] = Field(
        default_factory=lambda: get_secret("SOLANA_WALLET_ADDRESS", "solana_wallet_address.txt"),
        alias="SOLANA_WALLET_ADDRESS"
    )
    wallet_address: Optional[str] = Field(
        default_factory=lambda: get_secret("WALLET_ADDRESS", "wallet_address.txt"),
        alias="WALLET_ADDRESS"
    )
    
    def validate(self) -> list[str]:
        """Check required configuration. Returns list of missing items."""
        missing = []
        
        if not self.asgard_api_key:
            missing.append("asgard_api_key.txt")
        if not self.solana_rpc_url:
            missing.append("solana_rpc_url.txt")
        if not self.arbitrum_rpc_url:
            missing.append("arbitrum_rpc_url.txt")
        if not self.privy_app_id:
            missing.append("privy_app_id.txt")
        if not self.privy_app_secret:
            missing.append("privy_app_secret.txt")
        
        auth_key_path = SECRETS_DIR / "privy_auth.pem"
        if not auth_key_path.exists():
            missing.append("privy_auth.pem")
        
        return missing


# Global instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings."""
    global _settings
    _settings = Settings()
    return _settings


# Risk configuration loaded from YAML
_risk_config: Optional[dict] = None


def load_risk_config() -> dict:
    """Load risk configuration from YAML file."""
    global _risk_config
    if _risk_config is None:
        risk_yaml_path = BASE_DIR / "shared" / "config" / "risk.yaml"
        if not risk_yaml_path.exists():
            raise FileNotFoundError(f"Risk config not found: {risk_yaml_path}")
        
        import yaml
        with open(risk_yaml_path, "r") as f:
            _risk_config = yaml.safe_load(f)
    
    return _risk_config


def get_risk_limits() -> dict:
    """Get risk limits section from config."""
    return load_risk_config().get("risk_limits", {})


def get_funding_config() -> dict:
    """Get funding rate config section."""
    return load_risk_config().get("funding", {})
