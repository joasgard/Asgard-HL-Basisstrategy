"""
Stuck bridge deposit reconciliation service (N3).

If a bridge deposit tx confirms on Arbitrum but HL doesn't credit within
5 minutes, the deposit is stuck at `bridge_confirmed`. This background
service re-polls HL every 60 seconds and alerts if stuck > 30 minutes.

Designed to run as an asyncio task during bot startup.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from shared.db.database import Database
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# How often to check for stuck deposits
RECONCILE_INTERVAL_SECONDS = 60

# A deposit is "stuck" if bridge_confirmed but no HL credit after this long
STUCK_THRESHOLD_MINUTES = 5

# Alert at WARNING level if stuck beyond this
ALERT_THRESHOLD_MINUTES = 30


async def reconcile_stuck_deposits(db: Database) -> dict:
    """
    Check for deposits stuck at bridge_confirmed and re-poll HL.

    Returns:
        Summary dict with counts.
    """
    # Find deposits where bridge tx confirmed but HL hasn't credited,
    # and the deposit is at least STUCK_THRESHOLD_MINUTES old
    cutoff = datetime.utcnow() - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
    alert_cutoff = datetime.utcnow() - timedelta(minutes=ALERT_THRESHOLD_MINUTES)

    rows = await db.fetchall(
        """SELECT dh.id, dh.user_id, dh.amount_usdc, dh.bridge_tx_hash,
                  dh.created_at, dh.status
           FROM deposit_history dh
           WHERE dh.direction = 'deposit'
             AND dh.deposit_stage = 'bridge_confirmed'
             AND dh.created_at < $1
           ORDER BY dh.created_at ASC""",
        (cutoff,),
    )

    if not rows:
        return {"checked": 0, "reconciled": 0, "still_stuck": 0}

    logger.info(
        "deposit_reconciler_check",
        stuck_count=len(rows),
    )

    reconciled = 0
    still_stuck = 0

    for row in rows:
        job_id = row["id"]
        user_id = row["user_id"]
        amount = row["amount_usdc"]
        created_at = row["created_at"]

        try:
            from bot.venues.user_context import UserTradingContext

            async with await UserTradingContext.from_user_id(user_id, db) as ctx:
                trader = ctx.get_hl_trader()
                hl_balance = await trader.get_deposited_balance()

            # If HL has balance, mark as credited
            # (Simple heuristic — if balance > 0, the deposit likely went through)
            if hl_balance > 0:
                await db.execute(
                    """UPDATE deposit_history
                    SET deposit_stage = 'hl_credited',
                        status = 'completed',
                        completed_at = NOW()
                    WHERE id = $1 AND deposit_stage = 'bridge_confirmed'""",
                    (job_id,),
                )
                logger.info(
                    "deposit_reconciled",
                    job_id=job_id,
                    user_id=user_id,
                    amount_usdc=amount,
                    hl_balance=hl_balance,
                )
                reconciled += 1
            else:
                still_stuck += 1
                age_minutes = (datetime.utcnow() - created_at).total_seconds() / 60

                if created_at < alert_cutoff:
                    logger.warning(
                        "deposit_stuck_alert",
                        job_id=job_id,
                        user_id=user_id,
                        amount_usdc=amount,
                        bridge_tx_hash=row.get("bridge_tx_hash"),
                        stuck_minutes=round(age_minutes, 1),
                    )
                else:
                    logger.info(
                        "deposit_still_pending",
                        job_id=job_id,
                        user_id=user_id,
                        stuck_minutes=round(age_minutes, 1),
                    )

        except Exception as e:
            still_stuck += 1
            logger.error(
                "deposit_reconcile_error",
                job_id=job_id,
                user_id=user_id,
                error=str(e),
            )

    summary = {
        "checked": len(rows),
        "reconciled": reconciled,
        "still_stuck": still_stuck,
    }
    logger.info("deposit_reconciler_complete", **summary)
    return summary


async def run_deposit_reconciler_loop(
    check_interval: int = RECONCILE_INTERVAL_SECONDS,
) -> None:
    """
    Background loop that periodically checks for stuck deposits.

    Designed to be launched via ``asyncio.create_task()`` during bot startup.
    Runs indefinitely until cancelled.
    """
    db = Database()
    await db.connect()

    logger.info("deposit_reconciler_started", interval_seconds=check_interval)

    try:
        while True:
            try:
                await reconcile_stuck_deposits(db)
            except Exception as e:
                logger.error("deposit_reconciler_loop_error", error=str(e))
            await asyncio.sleep(check_interval)
    finally:
        await db.close()
