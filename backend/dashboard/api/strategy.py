"""Per-user strategy configuration API (7.1.2).

GET  /strategy         — current user's config (or defaults)
PUT  /strategy         — update config with validation + optimistic locking
POST /strategy/pause   — pause autonomous trading for current user
POST /strategy/resume  — resume autonomous trading for current user
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.dashboard.auth import get_current_user, User
from shared.config.strategy_defaults import (
    DEFAULTS,
    SYSTEM_MAX_LEVERAGE,
    SYSTEM_MAX_POSITIONS,
    SYSTEM_MAX_POSITION_USD,
    SYSTEM_MIN_COOLDOWN_MINUTES,
    SYSTEM_MIN_STOP_LOSS_PCT,
    to_dict,
)
from shared.db.database import get_db, Database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["strategy"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class StrategyConfigResponse(BaseModel):
    """Strategy config as returned by GET."""

    enabled: bool
    assets: List[str]
    protocols: Optional[List[str]]

    # Entry
    min_carry_apy: float
    min_funding_rate_8hr: float
    max_funding_volatility: float

    # Sizing
    max_position_pct: float
    max_concurrent_positions: int
    max_leverage: float

    # Exit
    min_exit_carry_apy: float
    take_profit_pct: Optional[float]
    stop_loss_pct: float

    # Recurse
    auto_reopen: bool
    cooldown_minutes: int

    # Meta
    version: int = 1
    is_default: bool = False  # True when no row exists for this user


class StrategyConfigUpdate(BaseModel):
    """Fields the user may update via PUT."""

    enabled: Optional[bool] = None
    assets: Optional[List[str]] = None
    protocols: Optional[List[str]] = None

    min_carry_apy: Optional[float] = Field(None, ge=0, le=200)
    min_funding_rate_8hr: Optional[float] = Field(None, ge=0)
    max_funding_volatility: Optional[float] = Field(None, ge=0, le=1)

    max_position_pct: Optional[float] = Field(None, gt=0, le=1)
    max_concurrent_positions: Optional[int] = Field(None, ge=1, le=SYSTEM_MAX_POSITIONS)
    max_leverage: Optional[float] = Field(None, ge=1.1, le=SYSTEM_MAX_LEVERAGE)

    min_exit_carry_apy: Optional[float] = Field(None, ge=0)
    take_profit_pct: Optional[float] = Field(None, ge=0)
    stop_loss_pct: Optional[float] = Field(None, ge=SYSTEM_MIN_STOP_LOSS_PCT, le=100)

    auto_reopen: Optional[bool] = None
    cooldown_minutes: Optional[int] = Field(None, ge=SYSTEM_MIN_COOLDOWN_MINUTES)

    # Optimistic locking — must match current version
    version: int

    @field_validator("assets")
    @classmethod
    def validate_assets(cls, v):
        allowed = {"SOL"}  # extend when more assets are supported
        if v is not None:
            unknown = set(v) - allowed
            if unknown:
                raise ValueError(f"Unknown assets: {unknown}")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/strategy", response_model=StrategyConfigResponse)
async def get_strategy(
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Return the current user's strategy config, or defaults if none set."""
    row = await db.fetchone(
        "SELECT * FROM user_strategy_config WHERE user_id = $1",
        (user.user_id,),
    )

    if not row:
        defaults = to_dict()
        return StrategyConfigResponse(**defaults, version=1, is_default=True)

    return StrategyConfigResponse(
        enabled=row["enabled"],
        assets=row["assets"] or DEFAULTS.assets,
        protocols=row["protocols"],
        min_carry_apy=row["min_carry_apy"],
        min_funding_rate_8hr=row["min_funding_rate_8hr"],
        max_funding_volatility=row["max_funding_volatility"],
        max_position_pct=row["max_position_pct"],
        max_concurrent_positions=row["max_concurrent_positions"],
        max_leverage=row["max_leverage"],
        min_exit_carry_apy=row["min_exit_carry_apy"],
        take_profit_pct=row["take_profit_pct"],
        stop_loss_pct=row["stop_loss_pct"],
        auto_reopen=row["auto_reopen"],
        cooldown_minutes=row["cooldown_minutes"],
        version=row["version"],
        is_default=False,
    )


@router.put("/strategy", response_model=StrategyConfigResponse)
async def update_strategy(
    body: StrategyConfigUpdate,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update strategy config with optimistic locking.

    The caller must supply the current ``version``. If it doesn't match the
    DB row the update is rejected (409 Conflict).
    """
    # Build SET clause from non-None fields (excluding version)
    updates = body.model_dump(exclude_none=True, exclude={"version"})
    if not updates:
        raise HTTPException(400, "No fields to update")

    # Check if row exists
    existing = await db.fetchone(
        "SELECT version FROM user_strategy_config WHERE user_id = $1",
        (user.user_id,),
    )

    if not existing:
        # First save — insert with provided values merged over defaults
        merged = to_dict()
        merged.update(updates)
        await db.execute(
            """INSERT INTO user_strategy_config
               (user_id, enabled, assets, protocols,
                min_carry_apy, min_funding_rate_8hr, max_funding_volatility,
                max_position_pct, max_concurrent_positions, max_leverage,
                min_exit_carry_apy, take_profit_pct, stop_loss_pct,
                auto_reopen, cooldown_minutes, version, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                       $11, $12, $13, $14, $15, 1, NOW())""",
            (
                user.user_id,
                merged["enabled"],
                merged["assets"],
                merged["protocols"],
                merged["min_carry_apy"],
                merged["min_funding_rate_8hr"],
                merged["max_funding_volatility"],
                merged["max_position_pct"],
                merged["max_concurrent_positions"],
                merged["max_leverage"],
                merged["min_exit_carry_apy"],
                merged["take_profit_pct"],
                merged["stop_loss_pct"],
                merged["auto_reopen"],
                merged["cooldown_minutes"],
            ),
        )
        logger.info("strategy_config_created user_id=%s", user.user_id)
    else:
        if existing["version"] != body.version:
            raise HTTPException(
                409,
                f"Config was modified by another request (expected version "
                f"{body.version}, current is {existing['version']}). "
                f"Please reload and try again.",
            )

        # Build dynamic UPDATE
        set_parts = []
        params = []
        idx = 1
        for col, val in updates.items():
            set_parts.append(f"{col} = ${idx}")
            params.append(val)
            idx += 1

        # Bump version and timestamp
        set_parts.append(f"version = version + 1")
        set_parts.append(f"updated_at = NOW()")

        # WHERE with optimistic lock
        params.append(user.user_id)
        params.append(body.version)
        where = f"user_id = ${idx} AND version = ${idx + 1}"

        sql = f"UPDATE user_strategy_config SET {', '.join(set_parts)} WHERE {where}"
        result = await db.execute(sql, tuple(params))

        logger.info(
            "strategy_config_updated user_id=%s version=%d fields=%s",
            user.user_id,
            body.version + 1,
            list(updates.keys()),
        )

    # Return fresh state
    return await get_strategy(user=user, db=db)


@router.get("/strategy/risk-status")
async def get_risk_status(
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Return current risk status for the dashboard (7.4.4)."""
    from bot.core.user_risk_manager import UserRiskManager

    mgr = UserRiskManager(db)
    status = await mgr.get_risk_status(user.user_id)

    # Also include paused state from strategy config
    config = await db.fetchone(
        "SELECT enabled, paused_at, paused_reason FROM user_strategy_config WHERE user_id = $1",
        (user.user_id,),
    )

    bot_status = "inactive"
    if config:
        if config.get("paused_at"):
            bot_status = "paused"
        elif config.get("enabled"):
            bot_status = "active"

    return {
        "bot_status": bot_status,
        "paused_reason": config.get("paused_reason") if config else None,
        **status,
    }


@router.post("/strategy/pause")
async def pause_strategy(
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Pause autonomous trading for the current user."""
    await db.execute(
        """INSERT INTO user_strategy_config (user_id, enabled, paused_at, paused_reason)
           VALUES ($1, FALSE, NOW(), 'user_requested')
           ON CONFLICT (user_id)
           DO UPDATE SET enabled = FALSE, paused_at = NOW(),
                         paused_reason = 'user_requested', updated_at = NOW()""",
        (user.user_id,),
    )
    logger.info("strategy_paused user_id=%s", user.user_id)
    return {"success": True, "message": "Strategy paused"}


@router.post("/strategy/resume")
async def resume_strategy(
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Resume autonomous trading for the current user."""
    await db.execute(
        """INSERT INTO user_strategy_config (user_id, enabled, paused_at, paused_reason)
           VALUES ($1, TRUE, NULL, NULL)
           ON CONFLICT (user_id)
           DO UPDATE SET enabled = TRUE, paused_at = NULL,
                         paused_reason = NULL, updated_at = NOW()""",
        (user.user_id,),
    )
    logger.info("strategy_resumed user_id=%s", user.user_id)
    return {"success": True, "message": "Strategy resumed"}
