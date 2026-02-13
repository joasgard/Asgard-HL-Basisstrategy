"""Positions API endpoints."""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import uuid
import json
import logging

from backend.dashboard.auth import require_viewer, require_operator
from backend.dashboard.dependencies import require_bot_bridge
from backend.dashboard.events_manager import (
    publish_position_opened, publish_position_closed
)
from shared.common.schemas import User, PositionSummary, PositionDetail
from shared.db.database import get_db, Database
from bot.core.errors import ErrorCode, AsgardError, get_error_info

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/positions", tags=["positions"])


# ---------------------------------------------------------------------------
# DB fallback helpers (used when bot bridge is unavailable)
# ---------------------------------------------------------------------------

def _row_to_position_summary(row: Dict[str, Any]) -> PositionSummary:
    """Convert a DB positions row to a PositionSummary with placeholder live data."""
    data = {}
    if row.get("data"):
        try:
            data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        except (json.JSONDecodeError, TypeError):
            pass

    opened_at = row.get("created_at") or datetime.utcnow()
    hold_hours = (datetime.utcnow() - opened_at).total_seconds() / 3600 if isinstance(opened_at, datetime) else 0

    return PositionSummary(
        position_id=row["id"],
        asset=data.get("asset", "SOL"),
        status="open",
        leverage=Decimal(str(data.get("leverage", 3))),
        deployed_usd=Decimal(str(data.get("size_usd", 0))),
        long_value_usd=Decimal("0"),
        short_value_usd=Decimal("0"),
        delta=Decimal("0"),
        delta_ratio=Decimal("0"),
        asgard_hf=Decimal("0"),
        hyperliquid_mf=Decimal("0"),
        total_pnl_usd=Decimal("0"),
        funding_pnl_usd=Decimal("0"),
        opened_at=opened_at,
        hold_duration_hours=round(hold_hours, 2),
    )


async def _list_positions_from_db(user_id: str, db: Database) -> List[PositionSummary]:
    """Read open positions from the database (no live data)."""
    rows = await db.fetchall(
        "SELECT id, user_id, data, created_at FROM positions WHERE user_id = $1 AND is_closed = 0",
        (user_id,),
    )
    return [_row_to_position_summary(r) for r in rows]


class OpenPositionRequest(BaseModel):
    """Request to open a new position."""
    asset: str = Field(..., description="Asset symbol (SOL, jitoSOL, jupSOL, INF)")
    leverage: float = Field(3.0, ge=1.1, le=4.0, description="Leverage multiplier (1.1x - 4x)")
    size_usd: float = Field(..., ge=100, description="Total position size in USD (both legs combined). Min $100.")
    venue: Optional[str] = Field(None, description="Preferred venue (kamino, drift, marginfi, solend)")


class OpenPositionResponse(BaseModel):
    """Response from opening a position."""
    success: bool
    message: str
    job_id: Optional[str] = None
    position_id: Optional[str] = None


class PreflightCheckResult(BaseModel):
    """Result of a single preflight check."""
    key: str
    label: str
    passed: bool
    error: Optional[str] = None


class PreflightResponse(BaseModel):
    """Response from preflight checks."""
    passed: bool
    checks: List[PreflightCheckResult]


class JobStatusResponse(BaseModel):
    """Status of a position opening job."""
    job_id: str
    status: str  # pending, running, completed, failed, cancelled
    position_id: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    error_stage: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    params: Optional[dict] = None


@router.get("", response_model=List[PositionSummary])
async def list_positions(
    user: User = Depends(require_viewer),
    db: Database = Depends(get_db),
):
    """
    List all open positions for the authenticated user.
    Requires viewer role or higher.

    Tries bot bridge first (live data); falls back to DB records.
    """
    from backend.dashboard.dependencies import get_bot_bridge

    bot_bridge = get_bot_bridge()
    if bot_bridge:
        try:
            positions = await bot_bridge.get_positions(user_id=user.user_id)
            return list(positions.values())
        except Exception:
            pass  # Fall through to DB query

    # Fallback: read positions from database
    return await _list_positions_from_db(user.user_id, db)


@router.get("/{position_id}", response_model=PositionDetail)
async def get_position(
    position_id: str,
    user: User = Depends(require_viewer),
    db: Database = Depends(get_db),
):
    """
    Get detailed information for a specific position.
    Requires viewer role or higher.
    """
    from backend.dashboard.dependencies import get_bot_bridge

    bot_bridge = get_bot_bridge()
    if bot_bridge:
        try:
            positions = await bot_bridge.get_positions(user_id=user.user_id)
            if position_id not in positions:
                raise HTTPException(404, "Position not found")
            detail = await bot_bridge.get_position_detail(position_id)
            return detail
        except HTTPException:
            raise
        except Exception:
            pass  # Fall through to DB query

    # Fallback: read from database
    row = await db.fetchone(
        "SELECT id, user_id, data, created_at FROM positions WHERE id = $1 AND user_id = $2",
        (position_id, user.user_id),
    )
    if not row:
        raise HTTPException(404, "Position not found")
    summary = _row_to_position_summary(row)
    return PositionDetail(
        **summary.model_dump(),
        sizing={}, asgard={}, hyperliquid={}, pnl={}, risk={},
    )


@router.post("/open", response_model=OpenPositionResponse)
async def open_position(
    request: OpenPositionRequest,
    user: User = Depends(require_operator),
    db: Database = Depends(get_db)
):
    """
    Open a new delta-neutral position.

    This creates an async job that will:
    1. Fetch current market rates
    2. Run preflight checks
    3. Open Asgard long position
    4. Open Hyperliquid short position
    5. Return position details

    Returns a job_id that can be polled via /jobs/{job_id}
    """
    job_id = str(uuid.uuid4())

    try:
        # Per-user position lock — prevent concurrent opens (e.g. double-click)
        from shared.redis_client import get_redis
        redis = await get_redis()
        lock_key = f"user:{user.user_id}:position_lock"
        acquired = await redis.set(lock_key, job_id, nx=True, ex=30)
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="A position operation is already in progress for your account.",
            )

        # Create job record
        await db.execute(
            """
            INSERT INTO position_jobs
            (job_id, user_id, status, params, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            (job_id, user.user_id, "pending", request.model_dump_json())
        )

        # Trigger background execution (releases lock on completion)
        asyncio.create_task(_execute_position_job(job_id, request, user.user_id, db))

        logger.info(f"Created position job {job_id} for user {user.user_id}")

        return OpenPositionResponse(
            success=True,
            message="Position opening initiated. Poll /positions/jobs/{job_id} for status.",
            job_id=job_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create position job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create position")


@router.post("/preflight", response_model=PreflightResponse)
async def run_preflight(
    request: OpenPositionRequest,
    user: User = Depends(require_operator),
    db: Database = Depends(get_db),
):
    """
    Run preflight checks without opening a position.

    Returns structured per-check results so the UI can display a checklist.
    """
    from bot.venues.user_context import UserTradingContext
    from bot.core.position_manager import PositionManager

    try:
        ctx = await UserTradingContext.from_user_id(user.user_id, db)
    except (ValueError, ImportError) as e:
        logger.warning(f"Cannot create trading context for preflight: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    try:
        async with ctx:
            pm = PositionManager.from_user_context(ctx)
            await pm.__aenter__()
            try:
                opportunity, _asset, _protocol = _build_opportunity(
                    f"preflight-{uuid.uuid4()}", request
                )
                result = await pm.run_preflight_checks(opportunity)
            finally:
                await pm.__aexit__(None, None, None)
    except Exception as e:
        logger.error(f"Preflight checks crashed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Preflight checks failed unexpectedly")

    # Map flat errors list back to individual checks.
    # run_preflight_checks appends one error per failed check, in order.
    error_iter = iter(result.errors)
    checks: List[PreflightCheckResult] = []
    for key, label in _CHECK_LABELS.items():
        passed = result.checks.get(key, False)
        error = None if passed else next(error_iter, None)
        checks.append(PreflightCheckResult(key=key, label=label, passed=passed, error=error))

    return PreflightResponse(passed=result.passed, checks=checks)


def _map_error_to_code(error_msg: str, stage: str) -> str:
    """Map error message to error code."""
    error_lower = error_msg.lower()

    # Wallet/Auth errors
    if "wallet not connected" in error_lower or "unauthorized" in error_lower:
        return "WAL-0004"
    if "insufficient sol" in error_lower or "not enough sol" in error_lower:
        return "WAL-0001"
    if "insufficient usdc" in error_lower or "not enough usdc" in error_lower:
        return "WAL-0002"
    if "insufficient eth" in error_lower:
        return "WAL-0003"

    # Asgard errors
    if stage == "asgard":
        if "insufficient liquidity" in error_lower:
            return "ASG-0002"
        if "health factor" in error_lower:
            return "ASG-0009"
        if "collateral" in error_lower:
            return "ASG-0008"
        if "transaction" in error_lower and "timeout" in error_lower:
            return "ASG-0007"
        if "sign" in error_lower:
            return "ASG-0005"
        if "submit" in error_lower:
            return "ASG-0006"
        if "build" in error_lower:
            return "ASG-0004"
        return "ASG-0003"

    # Hyperliquid errors
    if stage == "hyperliquid":
        if "insufficient margin" in error_lower:
            return "HLQ-0003"
        if "leverage" in error_lower:
            return "HLQ-0004"
        if "order" in error_lower:
            return "HLQ-0005"
        if "retry" in error_lower or "exhausted" in error_lower:
            return "HLQ-0006"
        return "HLQ-0002"

    # Risk errors
    if stage == "risk_check":
        if "funding rate" in error_lower:
            return "RSK-0002"
        if "price deviation" in error_lower:
            return "RSK-0003"
        if "volatility" in error_lower:
            return "RSK-0004"
        if "circuit breaker" in error_lower:
            return "RSK-0005"
        if "maximum positions" in error_lower or "max positions" in error_lower:
            return "RSK-0006"
        return "RSK-0001"

    # Network errors
    if "rate limit" in error_lower:
        return "NET-0004"
    if "solana" in error_lower and ("rpc" in error_lower or "network" in error_lower):
        return "NET-0002"
    if "arbitrum" in error_lower and ("rpc" in error_lower or "network" in error_lower):
        return "NET-0003"
    if "network" in error_lower or "connection" in error_lower:
        return "NET-0001"

    # Validation errors
    if "leverage" in error_lower and ("invalid" in error_lower or "range" in error_lower):
        return "VAL-0003"
    if "size" in error_lower:
        if "small" in error_lower or "minimum" in error_lower:
            return "VAL-0005"
        if "large" in error_lower or "maximum" in error_lower:
            return "VAL-0006"
        return "VAL-0004"

    # Default
    return "GEN-0001"


def _build_opportunity(job_id: str, request: OpenPositionRequest):
    """Build an ArbitrageOpportunity from an open-position request.

    Returns (opportunity, asset_enum, selected_protocol).
    """
    from shared.config.assets import Asset
    from shared.models.common import Protocol
    from shared.models.funding import FundingRate, AsgardRates
    from shared.models.opportunity import ArbitrageOpportunity, OpportunityScore

    asset = Asset(request.asset.upper())

    venue_map = {
        "marginfi": Protocol.MARGINFI,
        "kamino": Protocol.KAMINO,
        "solend": Protocol.SOLEND,
        "drift": Protocol.DRIFT,
    }
    selected_protocol = venue_map.get(
        (request.venue or "").lower(), Protocol.KAMINO
    )

    deployed_capital = Decimal(str(request.size_usd))
    leverage_dec = Decimal(str(request.leverage))
    position_size = deployed_capital * leverage_dec

    current_funding = FundingRate(
        timestamp=datetime.utcnow(),
        coin=asset.value,
        rate_8hr=Decimal("-0.0001"),
    )

    asgard_rates = AsgardRates(
        protocol_id=selected_protocol.value,
        token_a_mint="",
        token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        token_a_lending_apy=Decimal("0.05"),
        token_b_borrowing_apy=Decimal("0.08"),
        token_b_max_borrow_capacity=position_size * 2,
    )

    opportunity = ArbitrageOpportunity(
        id=f"direct-{job_id}",
        asset=asset,
        selected_protocol=selected_protocol,
        asgard_rates=asgard_rates,
        current_funding=current_funding,
        funding_volatility=Decimal("0.3"),
        leverage=leverage_dec,
        deployed_capital_usd=deployed_capital,
        position_size_usd=position_size,
        score=OpportunityScore(
            funding_apy=abs(current_funding.rate_annual),
            net_carry_apy=Decimal("0"),
        ),
        price_deviation=Decimal("0"),
        preflight_checks_passed=False,
    )

    return opportunity, asset, selected_protocol


# Check label mapping (insertion-ordered to match run_preflight_checks)
_CHECK_LABELS = {
    "wallet_balance": "Wallet balances",
    "price_consensus": "Price consensus",
    "funding_validation": "Funding rates",
    "protocol_capacity": "Protocol capacity",
    "fee_market": "Fee market",
    "opportunity_simulation": "Position simulation",
}


async def _execute_position_direct(
    job_id: str,
    request: OpenPositionRequest,
    user_id: str,
    db: Database,
) -> dict:
    """
    Execute position opening directly using user's wallets (SaaS mode).

    Creates a UserTradingContext for the user, builds a PositionManager
    with their wallet-specific signers, and executes the trade.
    """
    from bot.venues.user_context import UserTradingContext
    from bot.core.position_manager import PositionManager

    # Resolve user's wallets
    ctx = await UserTradingContext.from_user_id(user_id, db)

    async with ctx:
        # Create per-user position manager
        pm = PositionManager.from_user_context(ctx)
        await pm.__aenter__()

        try:
            opportunity, _asset, _protocol = _build_opportunity(job_id, request)

            # Run preflight checks
            preflight = await pm.run_preflight_checks(opportunity)
            if not preflight.passed:
                errors = "; ".join(preflight.errors)
                return {
                    "success": False,
                    "error": f"Preflight checks failed: {errors}",
                    "stage": "preflight",
                }

            # Execute position opening
            result = await pm.open_position(opportunity=opportunity)

            if result.success and result.position:
                position = result.position
                position.user_id = user_id

                # Persist to DB
                await db.execute(
                    """INSERT INTO positions (id, user_id, data, created_at, updated_at)
                       VALUES ($1, $2, $3, NOW(), NOW())""",
                    (position.position_id, user_id, json.dumps(position.to_dict()
                     if hasattr(position, 'to_dict') else str(position)))
                )

                return {
                    "success": True,
                    "position_id": position.position_id,
                    "selected_protocol": request.venue,
                }
            else:
                return {
                    "success": False,
                    "error": result.error or "Unknown error",
                    "stage": result.stage or "execution",
                }
        finally:
            await pm.__aexit__(None, None, None)


async def _execute_position_job(
    job_id: str,
    request: OpenPositionRequest,
    user_id: str,
    db: Database
):
    """
    Execute position opening job in background.

    Tries direct execution (SaaS mode with per-user wallets) first.
    Falls back to bot bridge (single-tenant mode) if direct execution
    is not possible (e.g., user wallets not configured).
    """
    from backend.dashboard.dependencies import get_bot_bridge

    try:
        # Update status to running
        await db.execute(
            "UPDATE position_jobs SET status = $1, started_at = NOW() WHERE job_id = $2",
            ("running", job_id)
        )

        # Try direct execution first (SaaS mode)
        try:
            result = await _execute_position_direct(job_id, request, user_id, db)
        except (ValueError, ImportError) as e:
            logger.info(f"Direct execution not available ({e}), falling back to bot bridge")
            result = None

        # Fall back to bot bridge if direct execution didn't work
        if result is None:
            bot_bridge = get_bot_bridge()
            if not bot_bridge:
                error_code = "GEN-0002"
                error_info = get_error_info(ErrorCode(error_code))
                await db.execute(
                    """
                    UPDATE position_jobs
                    SET status = $1, error = $2, error_code = $3, completed_at = NOW()
                    WHERE job_id = $4
                    """,
                    ("failed", error_info["message"], error_code, job_id)
                )
                return

            result = await bot_bridge.open_position(
                asset=request.asset,
                leverage=request.leverage,
                size_usd=request.size_usd,
                protocol=request.venue,
                user_id=user_id
            )

        # Update job record with result
        if result.get("success"):
            await db.execute(
                """
                UPDATE position_jobs
                SET status = $1, position_id = $2, result = $3, completed_at = NOW()
                WHERE job_id = $4
                """,
                ("completed", result.get("position_id"), json.dumps(result), job_id)
            )

            # Publish event for real-time updates
            await publish_position_opened({
                "position_id": result.get("position_id"),
                "asset": request.asset,
                "leverage": request.leverage,
                "size_usd": request.size_usd,
                "protocol": result.get("selected_protocol"),
                "user_id": user_id
            })

            logger.info(f"Position job {job_id} completed successfully")
        else:
            # Failed - store error details with code
            error_stage = result.get("stage", "unknown")
            error_msg = result.get("error", "Unknown error")
            error_code = _map_error_to_code(error_msg, error_stage)

            await db.execute(
                """
                UPDATE position_jobs
                SET status = $1, error = $2, error_code = $3, error_stage = $4, result = $5, completed_at = NOW()
                WHERE job_id = $6
                """,
                ("failed", error_msg, error_code, error_stage, json.dumps(result), job_id)
            )
            logger.error(f"Position job {job_id} failed at stage {error_stage}: {error_msg} ({error_code})")

    except Exception as e:
        logger.error(f"Position job {job_id} crashed: {e}", exc_info=True)
        error_msg = str(e)
        error_code = _map_error_to_code(error_msg, "unknown")
        try:
            await db.execute(
                """
                UPDATE position_jobs
                SET status = $1, error = $2, error_code = $3, completed_at = NOW()
                WHERE job_id = $4
                """,
                ("failed", error_msg, error_code, job_id)
            )
        except Exception:
            pass  # Best effort
    finally:
        # Release per-user position lock
        try:
            from shared.redis_client import get_redis
            redis = await get_redis()
            await redis.delete(f"user:{user_id}:position_lock")
        except Exception:
            pass


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    user: User = Depends(require_viewer),
    db: Database = Depends(get_db)
):
    """Get status of a position opening job."""
    row = await db.fetchone(
        """
        SELECT job_id, user_id, status, position_id, error, error_code, error_stage,
               created_at, completed_at, params
        FROM position_jobs WHERE job_id = $1
        """,
        (job_id,)
    )

    if not row:
        raise HTTPException(404, "Job not found")

    # Verify user owns this job
    if row.get("user_id") and row["user_id"] != user.user_id:
        raise HTTPException(404, "Job not found")

    # Parse params JSON
    params = None
    if row["params"]:
        try:
            params = json.loads(row["params"]) if isinstance(row["params"], str) else row["params"]
        except (json.JSONDecodeError, TypeError):
            pass

    return JobStatusResponse(
        job_id=row["job_id"],
        status=row["status"],
        position_id=row["position_id"],
        error=row["error"],
        error_code=row.get("error_code"),
        error_stage=row["error_stage"],
        created_at=str(row["created_at"]) if row["created_at"] else None,
        completed_at=str(row["completed_at"]) if row["completed_at"] else None,
        params=params
    )


class ClosePositionResponse(BaseModel):
    """Response from closing a position."""
    success: bool
    message: str
    position_id: str
    job_id: Optional[str] = None


@router.post("/{position_id}/close", response_model=ClosePositionResponse)
async def close_position(
    position_id: str,
    user: User = Depends(require_operator),
    db: Database = Depends(get_db)
):
    """
    Close a delta-neutral position.

    This creates an async job that will:
    1. Close Hyperliquid short position
    2. Close Asgard long position
    3. Return completion status

    Returns a job_id that can be polled via /jobs/{job_id}
    """
    job_id = str(uuid.uuid4())

    try:
        # Verify position belongs to user
        bot_bridge = require_bot_bridge()
        user_positions = await bot_bridge.get_positions(user_id=user.user_id)
        if position_id not in user_positions:
            raise HTTPException(404, "Position not found or does not belong to user")

        # Create job record
        await db.execute(
            """
            INSERT INTO position_jobs
            (job_id, user_id, status, params, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            (job_id, user.user_id, "pending", json.dumps({
                "action": "close",
                "position_id": position_id
            }))
        )

        # Trigger background execution
        asyncio.create_task(_execute_close_job(job_id, position_id, user.user_id, db))

        logger.info(f"Created close job {job_id} for position {position_id}, user {user.user_id}")

        return ClosePositionResponse(
            success=True,
            message="Position closing initiated. Poll /positions/jobs/{job_id} for status.",
            position_id=position_id,
            job_id=job_id
        )

    except Exception as e:
        logger.error(f"Failed to create close job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create close job")


def _map_close_error_to_code(error_msg: str) -> str:
    """Map close error message to error code."""
    error_lower = error_msg.lower()

    if "wallet not connected" in error_lower:
        return "WAL-0004"
    if "position not found" in error_lower:
        return "POS-0001"
    if "already closed" in error_lower:
        return "POS-0002"
    if "unwind" in error_lower:
        return "POS-0004"
    if "asymmetric" in error_lower:
        return "POS-0005"
    if "hyperliquid" in error_lower:
        return "HLQ-0007"
    if "asgard" in error_lower:
        return "ASG-0003"
    return "POS-0003"


async def _execute_close_job(
    job_id: str,
    position_id: str,
    user_id: str,
    db: Database
):
    """Execute position closing job in background."""
    from backend.dashboard.dependencies import get_bot_bridge

    try:
        # Update status to running
        await db.execute(
            "UPDATE position_jobs SET status = $1, started_at = NOW() WHERE job_id = $2",
            ("running", job_id)
        )

        # Get bot bridge
        bot_bridge = get_bot_bridge()
        if not bot_bridge:
            error_code = "GEN-0002"
            error_info = get_error_info(ErrorCode(error_code))
            await db.execute(
                """
                UPDATE position_jobs
                SET status = $1, error = $2, error_code = $3, completed_at = NOW()
                WHERE job_id = $4
                """,
                ("failed", error_info["message"], error_code, job_id)
            )
            return

        # Call bot to close position
        result = await bot_bridge.close_position(
            position_id=position_id,
            reason="manual"
        )

        # Update job record with result
        if result.get("success"):
            await db.execute(
                """
                UPDATE position_jobs
                SET status = $1, result = $2, completed_at = NOW()
                WHERE job_id = $3
                """,
                ("completed", json.dumps(result), job_id)
            )

            # Publish event for real-time updates
            await publish_position_closed(
                position_id=position_id,
                pnl_data={
                    "total_pnl": result.get("total_pnl", 0),
                    "user_id": user_id
                }
            )

            logger.info(f"Close job {job_id} completed successfully")
        else:
            error_msg = result.get("error", "Unknown error")
            error_code = _map_close_error_to_code(error_msg)
            await db.execute(
                """
                UPDATE position_jobs
                SET status = $1, error = $2, error_code = $3, result = $4, completed_at = NOW()
                WHERE job_id = $5
                """,
                ("failed", error_msg, error_code, json.dumps(result), job_id)
            )
            logger.error(f"Close job {job_id} failed: {error_msg} ({error_code})")

    except Exception as e:
        logger.error(f"Close job {job_id} crashed: {e}", exc_info=True)
        error_msg = str(e)
        error_code = _map_close_error_to_code(error_msg)
        try:
            await db.execute(
                """
                UPDATE position_jobs
                SET status = $1, error = $2, error_code = $3, completed_at = NOW()
                WHERE job_id = $4
                """,
                ("failed", error_msg, error_code, job_id)
            )
        except Exception:
            pass  # Best effort


class CloseAllResponse(BaseModel):
    """Response from closing all positions."""
    success: bool
    message: str
    positions_closed: int = 0
    job_ids: List[str] = []


@router.post("/close-all", response_model=CloseAllResponse)
async def close_all_positions(
    user: User = Depends(require_operator),
    db: Database = Depends(get_db),
):
    """
    Emergency close ALL open positions for the current user.

    Pauses the strategy first, then closes each position sequentially.
    """
    # Pause strategy immediately to prevent new entries
    await db.execute(
        """INSERT INTO user_strategy_config (user_id, enabled, paused_at, paused_reason)
           VALUES ($1, FALSE, NOW(), 'emergency_close_all')
           ON CONFLICT (user_id)
           DO UPDATE SET enabled = FALSE, paused_at = NOW(),
                         paused_reason = 'emergency_close_all', updated_at = NOW()""",
        (user.user_id,),
    )

    # Get all open positions for this user
    rows = await db.fetchall(
        "SELECT id FROM positions WHERE user_id = $1 AND is_closed = 0",
        (user.user_id,),
    )

    if not rows:
        return CloseAllResponse(
            success=True,
            message="No open positions to close. Strategy paused.",
            positions_closed=0,
        )

    # Create close jobs for each position
    job_ids = []
    for row in rows:
        position_id = row["id"]
        job_id = str(uuid.uuid4())

        await db.execute(
            """INSERT INTO position_jobs (job_id, user_id, status, params, created_at)
               VALUES ($1, $2, 'pending', $3, NOW())""",
            (job_id, user.user_id, json.dumps({
                "action": "close",
                "position_id": position_id,
                "source": "emergency_close_all",
            })),
        )

        asyncio.create_task(
            _execute_close_job(job_id, position_id, user.user_id, db)
        )
        job_ids.append(job_id)

    logger.warning(
        "Emergency close-all for user %s: %d positions, jobs=%s",
        user.user_id, len(rows), job_ids,
    )

    return CloseAllResponse(
        success=True,
        message=f"Closing {len(rows)} position(s). Strategy paused.",
        positions_closed=len(rows),
        job_ids=job_ids,
    )


@router.get("/jobs", response_model=List[JobStatusResponse])
async def list_jobs(
    user: User = Depends(require_viewer),
    db: Database = Depends(get_db),
    limit: int = 10
):
    """List recent position opening jobs for the user."""
    rows = await db.fetchall(
        """
        SELECT job_id, status, position_id, error, error_code, error_stage,
               created_at, completed_at, params
        FROM position_jobs
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        (user.user_id, limit)
    )

    results = []
    for row in rows:
        params = None
        if row["params"]:
            try:
                params = json.loads(row["params"]) if isinstance(row["params"], str) else row["params"]
            except (json.JSONDecodeError, TypeError):
                pass

        results.append(JobStatusResponse(
            job_id=row["job_id"],
            status=row["status"],
            position_id=row["position_id"],
            error=row["error"],
            error_code=row.get("error_code"),
            error_stage=row["error_stage"],
            created_at=str(row["created_at"]) if row["created_at"] else None,
            completed_at=str(row["completed_at"]) if row["completed_at"] else None,
            params=params
        ))

    return results
