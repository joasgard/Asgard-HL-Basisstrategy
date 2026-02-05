"""Dashboard configuration."""

import os
from typing import Optional
from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings

from src.config.settings import get_secret


class DashboardSettings(BaseSettings):
    """Dashboard-specific settings (NO trading secrets)."""
    
    model_config = ConfigDict(env_file=".env")
    
    # Environment
    dashboard_env: str = Field(default="development", alias="DASHBOARD_ENV")
    
    # Server
    dashboard_host: str = Field(default="0.0.0.0", alias="DASHBOARD_HOST")
    dashboard_port: int = Field(default=8080, alias="DASHBOARD_PORT")
    
    # Bot connection
    bot_api_url: str = Field(default="http://bot:8000", alias="BOT_API_URL")
    
    # Auth secrets (dashboard-only, not trading keys)
    # NOTE: In production, these MUST be set to secure random values
    jwt_secret: str = Field(
        default_factory=lambda: _get_jwt_secret(),
        alias="DASHBOARD_JWT_SECRET"
    )
    session_secret: str = Field(
        default_factory=lambda: _get_session_secret(),
        alias="DASHBOARD_SESSION_SECRET"
    )
    
    # Bot admin key reference (for proxying control requests)
    bot_admin_key: str = Field(
        default_factory=lambda: _get_admin_key()
    )
    internal_token: str = Field(
        default_factory=lambda: _get_admin_key()
    )
    
    # Alert channels (optional)
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")
    alert_webhook_url: Optional[str] = Field(default=None, alias="ALERT_WEBHOOK_URL")
    discord_webhook_url: Optional[str] = Field(default=None, alias="DISCORD_WEBHOOK_URL")
    
    # Cache settings
    cache_ttl: float = Field(default=5.0, alias="CACHE_TTL")
    
    @field_validator('jwt_secret', 'session_secret')
    @classmethod
    def validate_secret(cls, v: str, info) -> str:
        """Validate that secrets are properly configured in production."""
        env = os.getenv("DASHBOARD_ENV", "development")
        
        if env == "production":
            # In production, reject default/weak secrets
            weak_secrets = [
                "dev-secret-change-in-production",
                "change-me",
                "default",
                "",
            ]
            
            if v in weak_secrets or len(v) < 32:
                raise ValueError(
                    f"{info.field_name} must be set to a secure random value "
                    f"(32+ characters) in production. "
                    f"Generate one with: openssl rand -hex 32"
                )
        
        return v


def _get_jwt_secret() -> str:
    """Get JWT secret from environment or secrets file."""
    # Try environment variable first
    secret = os.getenv("DASHBOARD_JWT_SECRET")
    if secret:
        return secret
    
    # Try secrets file
    secret = get_secret("DASHBOARD_JWT_SECRET", "dashboard_jwt.txt")
    if secret:
        return secret
    
    # Check environment
    env = os.getenv("DASHBOARD_ENV", "development")
    if env == "production":
        raise RuntimeError(
            "DASHBOARD_JWT_SECRET must be set in production. "
            "Generate one with: openssl rand -hex 32"
        )
    
    # Development fallback with warning
    import warnings
    warnings.warn(
        "Using development JWT secret. Set DASHBOARD_JWT_SECRET for production.",
        RuntimeWarning
    )
    return "dev-secret-change-in-production-NOT-FOR-PRODUCTION-USE"


def _get_session_secret() -> str:
    """Get session secret from environment or secrets file."""
    secret = os.getenv("DASHBOARD_SESSION_SECRET")
    if secret:
        return secret
    
    secret = get_secret("DASHBOARD_SESSION_SECRET", "dashboard_session.txt")
    if secret:
        return secret
    
    env = os.getenv("DASHBOARD_ENV", "development")
    if env == "production":
        raise RuntimeError(
            "DASHBOARD_SESSION_SECRET must be set in production. "
            "Generate one with: openssl rand -hex 32"
        )
    
    import warnings
    warnings.warn(
        "Using development session secret. Set DASHBOARD_SESSION_SECRET for production.",
        RuntimeWarning
    )
    return "dev-session-change-in-production-NOT-FOR-PRODUCTION-USE"


def _get_admin_key() -> str:
    """Get admin API key from environment or secrets file."""
    # Try environment variable first
    key = os.getenv("ADMIN_API_KEY")
    if key:
        return key
    
    # Try secrets file
    key = get_secret("ADMIN_API_KEY", "admin_api_key.txt")
    if key:
        return key
    
    # Check environment
    env = os.getenv("DASHBOARD_ENV", "development")
    if env == "production":
        raise RuntimeError(
            "ADMIN_API_KEY must be set in production. "
            "Generate one with: openssl rand -hex 32"
        )
    
    # Development fallback
    import warnings
    warnings.warn(
        "ADMIN_API_KEY not set. Dashboard controls will not work. "
        "Generate one with: openssl rand -hex 32",
        RuntimeWarning
    )
    return ""


# Singleton instance
_settings: Optional[DashboardSettings] = None


def get_dashboard_settings() -> DashboardSettings:
    """Get dashboard settings singleton."""
    global _settings
    if _settings is None:
        _settings = DashboardSettings()
    return _settings
