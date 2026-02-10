"""Settings API endpoints for strategy configuration."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from src.dashboard.auth import require_operator
from src.db.database import get_db, Database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])


class StrategySettings(BaseModel):
    """Strategy configuration settings."""
    default_leverage: float = Field(3.0, ge=1.1, le=4.0)
    max_position_size: int = Field(50000, ge=100)
    # Minimum position size = total deployed capital (both legs combined)
    min_position_size: int = Field(100, ge=100)
    max_positions_per_asset: int = Field(1, ge=1, le=5)
    min_opportunity_apy: float = Field(1.0, ge=0)
    max_funding_volatility: float = Field(50.0, ge=0, le=100)
    price_deviation_threshold: float = Field(0.5, ge=0.1, le=5.0)
    delta_drift_threshold: float = Field(0.5, ge=0.1, le=5.0)
    enable_auto_exit: bool = True
    enable_circuit_breakers: bool = True


class SettingsResponse(BaseModel):
    """Settings response."""
    success: bool
    message: str
    settings: Optional[StrategySettings] = None


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    db: Database = Depends(get_db)
):
    """Get current strategy settings."""
    try:
        settings = await load_settings(db)
        return SettingsResponse(
            success=True,
            message="Settings loaded",
            settings=settings
        )
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        # Return defaults on error
        return SettingsResponse(
            success=True,
            message="Using default settings",
            settings=StrategySettings()
        )


@router.post("/settings", response_model=SettingsResponse)
async def save_settings(
    settings: StrategySettings,
    user = Depends(require_operator),
    db: Database = Depends(get_db)
):
    """Save strategy settings."""
    try:
        await store_settings(db, settings)
        
        # Audit log
        await db.execute(
            "INSERT INTO audit_log (action, user, details, success) VALUES (?, ?, ?, ?)",
            ("settings_update", user.user_id, f"leverage={settings.default_leverage}, max_size={settings.max_position_size}", True)
        )
        await db._connection.commit()
        
        return SettingsResponse(
            success=True,
            message="Settings saved successfully",
            settings=settings
        )
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/reset", response_model=SettingsResponse)
async def reset_settings(
    user = Depends(require_operator),
    db: Database = Depends(get_db)
):
    """Reset settings to defaults."""
    try:
        defaults = StrategySettings()
        await store_settings(db, defaults)
        
        # Audit log
        await db.execute(
            "INSERT INTO audit_log (action, user, details, success) VALUES (?, ?, ?, ?)",
            ("settings_reset", user.user_id, "Reset to defaults", True)
        )
        await db._connection.commit()
        
        return SettingsResponse(
            success=True,
            message="Settings reset to defaults",
            settings=defaults
        )
    except Exception as e:
        logger.error(f"Failed to reset settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def load_settings(db: Database) -> StrategySettings:
    """Load settings from database."""
    config_keys = [
        "default_leverage",
        "max_position_size",
        "min_position_size",
        "max_positions_per_asset",
        "min_opportunity_apy",
        "max_funding_volatility",
        "price_deviation_threshold",
        "delta_drift_threshold",
        "enable_auto_exit",
        "enable_circuit_breakers"
    ]
    
    settings_dict = {}
    for key in config_keys:
        value = await db.get_config(f"setting_{key}")
        if value is not None:
            # Convert string to appropriate type
            if key.startswith("enable_"):
                settings_dict[key] = value.lower() == "true"
            elif key in ["max_position_size", "min_position_size", "max_positions_per_asset"]:
                settings_dict[key] = int(value)
            else:
                settings_dict[key] = float(value)
    
    return StrategySettings(**settings_dict)


async def store_settings(db: Database, settings: StrategySettings) -> None:
    """Store settings in database."""
    settings_dict = settings.model_dump()
    
    for key, value in settings_dict.items():
        await db.set_config(f"setting_{key}", str(value))
