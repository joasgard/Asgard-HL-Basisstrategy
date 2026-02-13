"""
Per-user Risk Manager (7.3.1–7.3.5).

Enforces per-user risk limits that the autonomous scanner and position
monitor use before/after trades:

- **Drawdown** (7.3.1): Tracks peak balance (high-water mark). Pauses user
  if current balance drops more than ``RISK_MAX_DRAWDOWN_PCT`` below peak.
  Deposit/withdrawal adjustments prevent false triggers (N7).

- **Daily trade limit** (7.3.2): Counts trades per day. Blocks entry when
  ``RISK_MAX_DAILY_TRADES`` reached.

- **Circuit breaker** (7.3.3): Tracks consecutive execution failures.
  Pauses user after ``RISK_CIRCUIT_BREAKER_FAILURES`` in a row.

When any limit triggers a pause, sets ``user_strategy_config.paused_at``
and ``paused_reason`` (7.3.5).
"""
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from shared.config.strategy_defaults import (
    RISK_MAX_DRAWDOWN_PCT,
    RISK_MAX_DAILY_TRADES,
    RISK_CIRCUIT_BREAKER_FAILURES,
)

logger = logging.getLogger(__name__)


class UserRiskManager:
    """Per-user risk limit enforcement."""

    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------
    # 7.3.1: Drawdown tracking
    # ------------------------------------------------------------------

    async def check_drawdown(self, user_id: str, current_balance: float) -> bool:
        """Check if user has exceeded max drawdown from peak balance.

        Returns True if user is OK (no drawdown breach), False if paused.
        """
        row = await self.db.fetchone(
            "SELECT peak_balance_usd FROM user_risk_tracking WHERE user_id = $1",
            (user_id,),
        )

        if not row or float(row["peak_balance_usd"]) <= 0:
            # First check — initialise peak to current balance
            await self._upsert_risk_row(user_id, {
                "peak_balance_usd": current_balance,
                "current_balance_usd": current_balance,
            })
            return True

        peak = float(row["peak_balance_usd"])

        # Update current balance
        await self.db.execute(
            "UPDATE user_risk_tracking SET current_balance_usd = $1, updated_at = NOW() WHERE user_id = $2",
            (current_balance, user_id),
        )

        # Update peak if new high
        if current_balance > peak:
            await self.db.execute(
                "UPDATE user_risk_tracking SET peak_balance_usd = $1 WHERE user_id = $2",
                (current_balance, user_id),
            )
            return True

        # Check drawdown
        if peak > 0:
            drawdown_pct = ((peak - current_balance) / peak) * 100
            if drawdown_pct >= RISK_MAX_DRAWDOWN_PCT:
                await self._pause_for_risk(
                    user_id,
                    f"drawdown_limit: {drawdown_pct:.1f}% (peak=${peak:.0f}, current=${current_balance:.0f})",
                )
                return False

        return True

    async def update_peak_on_deposit(self, user_id: str, deposit_amount: float):
        """Adjust peak balance upward on deposit (N7).

        new_peak = old_peak + deposit_amount
        """
        await self.db.execute(
            """UPDATE user_risk_tracking
               SET peak_balance_usd = peak_balance_usd + $1,
                   current_balance_usd = current_balance_usd + $1,
                   updated_at = NOW()
               WHERE user_id = $2""",
            (deposit_amount, user_id),
        )

    async def update_peak_on_withdrawal(
        self, user_id: str, balance_before: float, balance_after: float
    ):
        """Adjust peak balance proportionally on withdrawal (N7).

        new_peak = old_peak * (balance_after / balance_before)
        """
        if balance_before <= 0:
            return

        ratio = balance_after / balance_before
        await self.db.execute(
            """UPDATE user_risk_tracking
               SET peak_balance_usd = peak_balance_usd * $1,
                   current_balance_usd = $2,
                   updated_at = NOW()
               WHERE user_id = $3""",
            (ratio, balance_after, user_id),
        )

    # ------------------------------------------------------------------
    # 7.3.2: Daily trade count
    # ------------------------------------------------------------------

    async def check_daily_trade_limit(self, user_id: str) -> bool:
        """Check if user is under the daily trade limit.

        Returns True if under limit, False if at/over limit.
        """
        row = await self.db.fetchone(
            "SELECT daily_trade_count, daily_trade_date FROM user_risk_tracking WHERE user_id = $1",
            (user_id,),
        )

        if not row:
            return True  # No record = no trades today

        trade_date = row["daily_trade_date"]
        today = date.today()

        # Reset counter if new day
        if trade_date is None or (
            isinstance(trade_date, date) and trade_date < today
        ):
            await self.db.execute(
                "UPDATE user_risk_tracking SET daily_trade_count = 0, daily_trade_date = $1 WHERE user_id = $2",
                (today, user_id),
            )
            return True

        return row["daily_trade_count"] < RISK_MAX_DAILY_TRADES

    async def record_trade(self, user_id: str):
        """Record a successful trade (increments daily count, resets failures)."""
        today = date.today()
        await self._upsert_risk_row(user_id, {
            "daily_trade_date": today,
        })

        # Increment count (reset if new day)
        await self.db.execute(
            """UPDATE user_risk_tracking
               SET daily_trade_count = CASE
                   WHEN daily_trade_date = $1 THEN daily_trade_count + 1
                   ELSE 1
               END,
               daily_trade_date = $1,
               consecutive_failures = 0,
               last_failure_reason = NULL,
               updated_at = NOW()
               WHERE user_id = $2""",
            (today, user_id),
        )

    # ------------------------------------------------------------------
    # 7.3.3: Consecutive failure circuit breaker
    # ------------------------------------------------------------------

    async def record_failure(self, user_id: str, reason: str) -> bool:
        """Record a trade execution failure.

        Returns True if user is still OK, False if circuit breaker tripped.
        """
        now = datetime.utcnow()
        await self._upsert_risk_row(user_id, {})

        await self.db.execute(
            """UPDATE user_risk_tracking
               SET consecutive_failures = consecutive_failures + 1,
                   last_failure_reason = $1,
                   last_failure_at = $2,
                   updated_at = NOW()
               WHERE user_id = $3""",
            (reason, now, user_id),
        )

        row = await self.db.fetchone(
            "SELECT consecutive_failures FROM user_risk_tracking WHERE user_id = $1",
            (user_id,),
        )

        if row and row["consecutive_failures"] >= RISK_CIRCUIT_BREAKER_FAILURES:
            await self._pause_for_risk(
                user_id,
                f"circuit_breaker: {row['consecutive_failures']} consecutive failures (last: {reason})",
            )
            return False

        return True

    async def record_success(self, user_id: str):
        """Record a successful trade execution (resets failure counter)."""
        await self._upsert_risk_row(user_id, {})
        await self.db.execute(
            """UPDATE user_risk_tracking
               SET consecutive_failures = 0, last_failure_reason = NULL, updated_at = NOW()
               WHERE user_id = $1""",
            (user_id,),
        )

    # ------------------------------------------------------------------
    # 7.3.5: Risk pause → dashboard notification
    # ------------------------------------------------------------------

    async def _pause_for_risk(self, user_id: str, reason: str):
        """Pause a user due to risk limit violation.

        Sets paused_at + paused_reason in user_strategy_config so the
        dashboard can display the reason.  Does NOT close existing
        positions — PositionMonitor handles those independently.
        """
        now = datetime.utcnow()
        logger.warning(
            "RISK PAUSE user %s: %s", user_id, reason,
        )

        # Update user_strategy_config (may not exist yet — upsert)
        await self.db.execute(
            """INSERT INTO user_strategy_config (user_id, paused_at, paused_reason)
               VALUES ($1, $2, $3)
               ON CONFLICT (user_id) DO UPDATE
               SET paused_at = $2, paused_reason = $3, updated_at = NOW()""",
            (user_id, now, reason),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _upsert_risk_row(self, user_id: str, fields: dict):
        """Ensure a risk tracking row exists for the user."""
        existing = await self.db.fetchone(
            "SELECT user_id FROM user_risk_tracking WHERE user_id = $1",
            (user_id,),
        )
        if not existing:
            await self.db.execute(
                """INSERT INTO user_risk_tracking (user_id, peak_balance_usd, current_balance_usd,
                       daily_trade_count, daily_trade_date)
                   VALUES ($1, $2, $3, 0, CURRENT_DATE)
                   ON CONFLICT (user_id) DO NOTHING""",
                (
                    user_id,
                    fields.get("peak_balance_usd", 0),
                    fields.get("current_balance_usd", 0),
                ),
            )

    async def get_risk_status(self, user_id: str) -> dict:
        """Get current risk status for dashboard display."""
        row = await self.db.fetchone(
            """SELECT peak_balance_usd, current_balance_usd,
                      daily_trade_count, daily_trade_date,
                      consecutive_failures, last_failure_reason
               FROM user_risk_tracking WHERE user_id = $1""",
            (user_id,),
        )

        if not row:
            return {
                "drawdown_pct": 0.0,
                "peak_balance_usd": 0.0,
                "daily_trades": 0,
                "daily_trade_limit": RISK_MAX_DAILY_TRADES,
                "consecutive_failures": 0,
            }

        peak = float(row["peak_balance_usd"] or 0)
        current = float(row["current_balance_usd"] or 0)
        drawdown = ((peak - current) / peak * 100) if peak > 0 else 0.0

        return {
            "drawdown_pct": round(drawdown, 2),
            "peak_balance_usd": round(peak, 2),
            "daily_trades": row["daily_trade_count"] or 0,
            "daily_trade_limit": RISK_MAX_DAILY_TRADES,
            "consecutive_failures": row["consecutive_failures"] or 0,
            "last_failure_reason": row["last_failure_reason"],
        }
