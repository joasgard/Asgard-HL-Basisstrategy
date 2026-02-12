"""Dashboard configuration with PostgreSQL and Redis support."""

import os
from pathlib import Path
from typing import Optional, List
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).parent.parent.parent
SECRETS_DIR = BASE_DIR / "secrets"


def load_secret(filename: str) -> Optional[str]:
    """Load secret from file."""
    path = SECRETS_DIR / filename
    if path.exists():
        return path.read_text().strip()
    return None


def get_server_secret() -> str:
    """Get server secret from file."""
    secret = load_secret("server_secret.txt")
    if not secret:
        raise RuntimeError(
            "server_secret.txt is required. Generate with: openssl rand -hex 32"
        )
    return secret


class DashboardSettings(BaseSettings):
    """Dashboard settings with production defaults."""

    model_config = ConfigDict(env_file=".env", extra="ignore")

    # Environment
    dashboard_env: str = Field(default="development", alias="DASHBOARD_ENV")

    # Server
    dashboard_host: str = Field(default="0.0.0.0", alias="DASHBOARD_HOST")
    dashboard_port: int = Field(default=8080, alias="DASHBOARD_PORT")

    # Bot connection
    bot_api_url: str = Field(default="http://localhost:8000", alias="BOT_API_URL")

    # Database (PostgreSQL)
    database_url: str = Field(
        default="postgresql://basis:basis@localhost:5432/basis",
        alias="DATABASE_URL",
    )
    db_pool_min: int = Field(default=2, alias="DB_POOL_MIN")
    db_pool_max: int = Field(default=10, alias="DB_POOL_MAX")

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379",
        alias="REDIS_URL",
    )

    # CORS
    allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
        alias="ALLOWED_ORIGINS",
    )

    # Secrets (all derived from server_secret.txt)
    jwt_secret: str = Field(default_factory=get_server_secret)
    session_secret: str = Field(default_factory=get_server_secret)
    internal_token: str = Field(default_factory=get_server_secret)

    # Bot admin API key (for control endpoints)
    bot_admin_key: str = Field(
        default_factory=lambda: load_secret("admin_api_key.txt") or "",
        alias="BOT_ADMIN_KEY",
    )

    # Cache
    cache_ttl: float = Field(default=5.0, alias="CACHE_TTL")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    def get_allowed_origins_list(self) -> List[str]:
        """Parse comma-separated origins into list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


# Singleton
_settings: Optional[DashboardSettings] = None


def get_dashboard_settings() -> DashboardSettings:
    """Get dashboard settings."""
    global _settings
    if _settings is None:
        _settings = DashboardSettings()
    return _settings
