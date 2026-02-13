"""
Funding API endpoints — deposit (Arb → HL) and withdraw (HL → Arb).

User-initiated bridge operations. Both run as async background jobs
with status polling, following the same pattern as position jobs.
"""
import asyncio
import json
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.dashboard.auth import get_current_user, User
from shared.db.database import get_db, Database
from shared.redis_client import get_redis
from shared.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/funding", tags=["funding"])

# System-wide per-deposit cap (N12). Deposits above this are rejected;
# user must split into multiple bridge operations.
MAX_AUTO_BRIDGE_USDC = float(os.environ.get("MAX_AUTO_BRIDGE_USDC", "25000"))


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class DepositRequest(BaseModel):
    """Request to bridge USDC from Arbitrum → Hyperliquid."""
    amount_usdc: float = Field(..., gt=0, description="Amount of USDC to deposit")


class WithdrawRequest(BaseModel):
    """Request to withdraw USDC from Hyperliquid → Arbitrum."""
    amount_usdc: float = Field(..., gt=0, description="Amount of USDC to withdraw")


class FundingJobResponse(BaseModel):
    """Response when a funding job is created."""
    job_id: str
    status: str
    message: str


class FundingJobStatus(BaseModel):
    """Status of a funding job."""
    job_id: str
    direction: str  # 'deposit' or 'withdraw'
    status: str  # pending / running / completed / failed
    amount_usdc: float
    error: Optional[str] = None
    approve_tx_hash: Optional[str] = None
    bridge_tx_hash: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


from typing import Optional


# ---------------------------------------------------------------------------
# POST /funding/deposit — bridge Arb → HL
# ---------------------------------------------------------------------------

@router.post("/deposit", response_model=FundingJobResponse)
async def deposit_to_hl(
    request: DepositRequest,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Initiate an Arbitrum → Hyperliquid USDC bridge deposit.

    Creates a background job. Poll GET /funding/jobs/{job_id} for status.
    """
    # N12: Cap per-deposit bridge amount
    if request.amount_usdc > MAX_AUTO_BRIDGE_USDC:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Maximum bridge deposit is ${MAX_AUTO_BRIDGE_USDC:,.0f} USDC per operation. "
                f"Requested: ${request.amount_usdc:,.0f}. Split into multiple deposits."
            ),
        )

    job_id = str(uuid.uuid4())

    # Prevent concurrent funding operations per user
    redis = await get_redis()
    lock_key = f"funding_lock:{user.user_id}"
    acquired = await redis.set(lock_key, job_id, nx=True, ex=600)  # 10 min TTL
    if not acquired:
        raise HTTPException(
            status_code=409,
            detail="A funding operation is already in progress. Please wait.",
        )

    try:
        await db.execute(
            """INSERT INTO deposit_history
            (id, user_id, direction, amount_usdc, status, created_at)
            VALUES ($1, $2, 'deposit', $3, 'pending', NOW())""",
            (job_id, user.user_id, request.amount_usdc),
        )
    except Exception as e:
        await redis.delete(lock_key)
        logger.error(f"Failed to create deposit job: {e}")
        raise HTTPException(500, "Failed to create deposit job")

    asyncio.create_task(
        _execute_deposit_job(job_id, request.amount_usdc, user.user_id, db, lock_key)
    )

    logger.info(
        f"Created deposit job {job_id}: {request.amount_usdc} USDC for user {user.user_id}"
    )

    return FundingJobResponse(
        job_id=job_id,
        status="pending",
        message="Deposit initiated. Poll /funding/jobs/{job_id} for status.",
    )


# ---------------------------------------------------------------------------
# POST /funding/withdraw — withdraw HL → Arb
# ---------------------------------------------------------------------------

@router.post("/withdraw", response_model=FundingJobResponse)
async def withdraw_from_hl(
    request: WithdrawRequest,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Initiate a Hyperliquid → Arbitrum USDC withdrawal.

    Blocked if user has open positions (margin would be locked).
    Creates a background job. Poll GET /funding/jobs/{job_id} for status.
    """
    # N9: Check available balance (accounts for margin in use)
    try:
        from bot.venues.user_context import UserTradingContext

        async with await UserTradingContext.from_user_id(user.user_id, db) as ctx:
            trader = ctx.get_hl_trader()
            withdrawable = await trader.get_withdrawable_balance()

        if request.amount_usdc > withdrawable:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Requested ${request.amount_usdc:,.2f} but only "
                    f"${withdrawable:,.2f} USDC is available for withdrawal "
                    f"(remaining balance is reserved as margin for open positions)."
                ),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check withdrawable balance: {e}")
        raise HTTPException(500, "Failed to check withdrawable balance")

    job_id = str(uuid.uuid4())

    redis = await get_redis()
    lock_key = f"funding_lock:{user.user_id}"
    acquired = await redis.set(lock_key, job_id, nx=True, ex=600)
    if not acquired:
        raise HTTPException(
            status_code=409,
            detail="A funding operation is already in progress. Please wait.",
        )

    try:
        await db.execute(
            """INSERT INTO deposit_history
            (id, user_id, direction, amount_usdc, status, created_at)
            VALUES ($1, $2, 'withdraw', $3, 'pending', NOW())""",
            (job_id, user.user_id, request.amount_usdc),
        )
    except Exception as e:
        await redis.delete(lock_key)
        logger.error(f"Failed to create withdraw job: {e}")
        raise HTTPException(500, "Failed to create withdraw job")

    asyncio.create_task(
        _execute_withdraw_job(job_id, request.amount_usdc, user.user_id, db, lock_key)
    )

    logger.info(
        f"Created withdraw job {job_id}: {request.amount_usdc} USDC for user {user.user_id}"
    )

    return FundingJobResponse(
        job_id=job_id,
        status="pending",
        message="Withdrawal initiated. Poll /funding/jobs/{job_id} for status.",
    )


# ---------------------------------------------------------------------------
# GET /funding/jobs/{job_id} — poll job status
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}", response_model=FundingJobStatus)
async def get_funding_job_status(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get the status of a deposit or withdrawal job."""
    row = await db.fetchone(
        """SELECT id, direction, status, amount_usdc, error,
                  approve_tx_hash, bridge_tx_hash, created_at, completed_at
           FROM deposit_history
           WHERE id = $1 AND user_id = $2""",
        (job_id, user.user_id),
    )

    if not row:
        raise HTTPException(404, "Job not found")

    return FundingJobStatus(
        job_id=row["id"],
        direction=row["direction"],
        status=row["status"],
        amount_usdc=row["amount_usdc"],
        error=row.get("error"),
        approve_tx_hash=row.get("approve_tx_hash"),
        bridge_tx_hash=row.get("bridge_tx_hash"),
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        completed_at=str(row["completed_at"]) if row.get("completed_at") else None,
    )


# ---------------------------------------------------------------------------
# GET /funding/history — list user's deposit/withdraw history
# ---------------------------------------------------------------------------

@router.get("/history")
async def get_funding_history(
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get deposit/withdrawal history for the current user."""
    rows = await db.fetchall(
        """SELECT id, direction, status, amount_usdc, error,
                  approve_tx_hash, bridge_tx_hash, created_at, completed_at
           FROM deposit_history
           WHERE user_id = $1
           ORDER BY created_at DESC
           LIMIT 20""",
        (user.user_id,),
    )

    return [
        FundingJobStatus(
            job_id=row["id"],
            direction=row["direction"],
            status=row["status"],
            amount_usdc=row["amount_usdc"],
            error=row.get("error"),
            approve_tx_hash=row.get("approve_tx_hash"),
            bridge_tx_hash=row.get("bridge_tx_hash"),
            created_at=str(row["created_at"]) if row.get("created_at") else None,
            completed_at=str(row["completed_at"]) if row.get("completed_at") else None,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Background job executors
# ---------------------------------------------------------------------------

async def _execute_deposit_job(
    job_id: str,
    amount_usdc: float,
    user_id: str,
    db: Database,
    lock_key: str,
):
    """Execute the bridge deposit in the background."""
    try:
        await db.execute(
            "UPDATE deposit_history SET status = 'running' WHERE id = $1",
            (job_id,),
        )

        from bot.venues.user_context import UserTradingContext

        async with await UserTradingContext.from_user_id(user_id, db) as ctx:
            depositor = ctx.get_hl_depositor()
            result = await depositor.deposit(amount_usdc)

        if result.success:
            # N3: Track deposit stage — bridge confirmed + HL credited
            stage = "hl_credited" if result.amount_usdc else "bridge_confirmed"
            await db.execute(
                """UPDATE deposit_history
                SET status = 'completed',
                    approve_tx_hash = $1,
                    bridge_tx_hash = $2,
                    deposit_stage = $3,
                    completed_at = NOW()
                WHERE id = $4""",
                (result.approve_tx_hash, result.deposit_tx_hash, stage, job_id),
            )
            logger.info(f"Deposit job {job_id} completed: {amount_usdc} USDC")
        else:
            # If we have a bridge tx hash, the bridge confirmed but HL didn't credit
            stage = "bridge_confirmed" if result.deposit_tx_hash else "initiated"
            await db.execute(
                """UPDATE deposit_history
                SET status = 'failed', error = $1,
                    deposit_stage = $2,
                    approve_tx_hash = $3,
                    bridge_tx_hash = $4,
                    completed_at = NOW()
                WHERE id = $5""",
                (result.error, stage, result.approve_tx_hash, result.deposit_tx_hash, job_id),
            )
            logger.error(f"Deposit job {job_id} failed: {result.error}")

    except Exception as e:
        logger.error(f"Deposit job {job_id} crashed: {e}", exc_info=True)
        try:
            await db.execute(
                """UPDATE deposit_history
                SET status = 'failed', error = $1, completed_at = NOW()
                WHERE id = $2""",
                (str(e), job_id),
            )
        except Exception:
            pass
    finally:
        try:
            redis = await get_redis()
            await redis.delete(lock_key)
        except Exception:
            pass


async def _execute_withdraw_job(
    job_id: str,
    amount_usdc: float,
    user_id: str,
    db: Database,
    lock_key: str,
):
    """Execute the HL withdrawal in the background."""
    try:
        await db.execute(
            "UPDATE deposit_history SET status = 'running' WHERE id = $1",
            (job_id,),
        )

        from bot.venues.user_context import UserTradingContext

        async with await UserTradingContext.from_user_id(user_id, db) as ctx:
            depositor = ctx.get_hl_depositor()
            result = await depositor.withdraw(amount_usdc)

        if result.success:
            await db.execute(
                """UPDATE deposit_history
                SET status = 'completed', completed_at = NOW()
                WHERE id = $1""",
                (job_id,),
            )
            logger.info(f"Withdraw job {job_id} completed: {amount_usdc} USDC")
        else:
            await db.execute(
                """UPDATE deposit_history
                SET status = 'failed', error = $1, completed_at = NOW()
                WHERE id = $2""",
                (result.error, job_id),
            )
            logger.error(f"Withdraw job {job_id} failed: {result.error}")

    except Exception as e:
        logger.error(f"Withdraw job {job_id} crashed: {e}", exc_info=True)
        try:
            await db.execute(
                """UPDATE deposit_history
                SET status = 'failed', error = $1, completed_at = NOW()
                WHERE id = $2""",
                (str(e), job_id),
            )
        except Exception:
            pass
    finally:
        try:
            redis = await get_redis()
            await redis.delete(lock_key)
        except Exception:
            pass
