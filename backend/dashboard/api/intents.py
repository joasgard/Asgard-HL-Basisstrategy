"""Intent API endpoints for intent-based position entry.

Users create intents specifying desired position parameters and entry criteria.
The IntentScanner service polls these intents and executes when conditions are met.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.dashboard.auth import require_viewer, require_operator
from backend.dashboard.api.balances import (
    _get_solana_balances, _get_arbitrum_balances, _check_sufficient_funds,
)
from shared.common.schemas import User
from shared.db.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intents", tags=["intents"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class CreateIntentRequest(BaseModel):
    """Request to create a new position intent."""
    asset: str = Field(default="SOL", description="Asset symbol (SOL, jitoSOL, jupSOL, INF)")
    leverage: float = Field(default=3.0, ge=1.1, le=4.0, description="Leverage multiplier")
    size_usd: float = Field(..., ge=100, description="Position size in USD. Min $100.")
    min_funding_rate: Optional[float] = Field(
        default=None,
        description="Minimum (most negative) funding rate required. E.g. -0.001 means shorts must earn at least 0.1%/8h.",
    )
    max_funding_volatility: Optional[float] = Field(
        default=0.50,
        description="Max 1-week funding rate volatility (0-1). Default 50%.",
    )
    max_entry_price: Optional[float] = Field(
        default=None,
        description="Max acceptable entry price for the asset.",
    )
    expires_in_hours: Optional[float] = Field(
        default=72,
        ge=1,
        le=720,
        description="Hours until intent expires. Default 72h (3 days). Max 720h (30 days).",
    )


class IntentResponse(BaseModel):
    """Response for a single intent."""
    id: str
    user_id: str
    asset: str
    leverage: float
    size_usd: float
    min_funding_rate: Optional[float]
    max_funding_volatility: Optional[float]
    max_entry_price: Optional[float]
    status: str
    position_id: Optional[str] = None
    execution_error: Optional[str] = None
    criteria_snapshot: Optional[dict] = None
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    activated_at: Optional[str] = None
    executed_at: Optional[str] = None


class CreateIntentResponse(BaseModel):
    """Response from creating an intent."""
    success: bool
    message: str
    intent_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=CreateIntentResponse)
async def create_intent(
    request: CreateIntentRequest,
    user: User = Depends(require_operator),
):
    """
    Create a new position intent.

    The intent will be picked up by the IntentScanner service, which checks
    entry criteria every 60 seconds and executes the position when all
    conditions are met.
    """
    db = get_db()
    intent_id = str(uuid.uuid4())

    # Calculate expiry
    expires_at = None
    if request.expires_in_hours:
        expires_at = datetime.utcnow() + timedelta(hours=request.expires_in_hours)

    # Preflight: check user has sufficient balance
    user_row = await db.fetchone(
        "SELECT solana_address, evm_address FROM users WHERE id = $1",
        (user.user_id,),
    )
    if not user_row:
        raise HTTPException(404, "User not found")

    solana_addr = user_row.get("solana_address")
    evm_addr = user_row.get("evm_address")

    solana_bal = await _get_solana_balances(solana_addr) if solana_addr else None
    arb_bal = await _get_arbitrum_balances(evm_addr) if evm_addr else None

    has_funds, reason = _check_sufficient_funds(solana_bal, arb_bal)
    if not has_funds:
        raise HTTPException(400, f"Insufficient funds: {reason}")

    # Check for duplicate active intents (same user + asset)
    existing = await db.fetchone(
        """SELECT id FROM position_intents
           WHERE user_id = $1 AND asset = $2 AND status IN ('pending', 'active')""",
        (user.user_id, request.asset),
    )
    if existing:
        raise HTTPException(
            409,
            f"Active intent already exists for {request.asset}. Cancel it first.",
        )

    await db.execute(
        """INSERT INTO position_intents
           (id, user_id, asset, leverage, size_usd, min_funding_rate,
            max_funding_volatility, max_entry_price, status, expires_at, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', $9, NOW())""",
        (
            intent_id,
            user.user_id,
            request.asset,
            request.leverage,
            request.size_usd,
            request.min_funding_rate,
            request.max_funding_volatility,
            request.max_entry_price,
            expires_at,
        ),
    )

    logger.info("Intent %s created for user %s: %s $%.0f @ %.1fx",
                intent_id, user.user_id, request.asset, request.size_usd, request.leverage)

    return CreateIntentResponse(
        success=True,
        message=f"Intent created. Will execute when conditions are met.",
        intent_id=intent_id,
    )


@router.get("", response_model=List[IntentResponse])
async def list_intents(
    status: Optional[str] = None,
    user: User = Depends(require_viewer),
):
    """
    List intents for the authenticated user.
    Optionally filter by status (pending, active, executed, cancelled, expired, failed).
    """
    db = get_db()

    if status:
        rows = await db.fetchall(
            """SELECT * FROM position_intents
               WHERE user_id = $1 AND status = $2
               ORDER BY created_at DESC""",
            (user.user_id, status),
        )
    else:
        rows = await db.fetchall(
            """SELECT * FROM position_intents
               WHERE user_id = $1
               ORDER BY created_at DESC""",
            (user.user_id,),
        )

    return [_row_to_response(row) for row in rows]


@router.get("/{intent_id}", response_model=IntentResponse)
async def get_intent(
    intent_id: str,
    user: User = Depends(require_viewer),
):
    """Get details for a specific intent."""
    db = get_db()
    row = await db.fetchone(
        "SELECT * FROM position_intents WHERE id = $1 AND user_id = $2",
        (intent_id, user.user_id),
    )
    if not row:
        raise HTTPException(404, "Intent not found")

    return _row_to_response(row)


@router.delete("/{intent_id}")
async def cancel_intent(
    intent_id: str,
    user: User = Depends(require_operator),
):
    """
    Cancel a pending or active intent.
    Cannot cancel an already executed, expired, or failed intent.
    """
    db = get_db()
    row = await db.fetchone(
        "SELECT id, status FROM position_intents WHERE id = $1 AND user_id = $2",
        (intent_id, user.user_id),
    )
    if not row:
        raise HTTPException(404, "Intent not found")

    if row["status"] not in ("pending", "active"):
        raise HTTPException(
            400,
            f"Cannot cancel intent in '{row['status']}' status",
        )

    await db.execute(
        """UPDATE position_intents
           SET status = 'cancelled', cancelled_at = NOW()
           WHERE id = $1""",
        (intent_id,),
    )

    logger.info("Intent %s cancelled by user %s", intent_id, user.user_id)
    return {"success": True, "message": "Intent cancelled"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_response(row) -> IntentResponse:
    """Convert a DB row to IntentResponse."""
    criteria = None
    if row["criteria_snapshot"]:
        try:
            criteria = json.loads(row["criteria_snapshot"]) if isinstance(row["criteria_snapshot"], str) else row["criteria_snapshot"]
        except (json.JSONDecodeError, TypeError):
            criteria = None

    return IntentResponse(
        id=row["id"],
        user_id=row["user_id"],
        asset=row["asset"],
        leverage=row["leverage"],
        size_usd=row["size_usd"],
        min_funding_rate=row["min_funding_rate"],
        max_funding_volatility=row["max_funding_volatility"],
        max_entry_price=row["max_entry_price"],
        status=row["status"],
        position_id=row.get("position_id"),
        execution_error=row.get("execution_error"),
        criteria_snapshot=criteria,
        expires_at=str(row["expires_at"]) if row.get("expires_at") else None,
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        activated_at=str(row["activated_at"]) if row.get("activated_at") else None,
        executed_at=str(row["executed_at"]) if row.get("executed_at") else None,
    )
