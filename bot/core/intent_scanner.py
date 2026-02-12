"""
Intent Scanner Service.

Polls the database for pending/active position intents and executes them
when entry criteria are met. Works in conjunction with the PositionMonitorService
(which handles exits) to provide the full lifecycle.

Entry criteria checked per intent:
1. Funding rate: current funding must be negative (shorts earn) and below
   the user's min_funding_rate threshold if specified.
2. Funding volatility: 1-week volatility must be below max_funding_volatility.
3. Entry price: current price must be below max_entry_price if specified.
4. Expiry: intent must not have expired.

Runs every SCAN_INTERVAL seconds:
1. Fetch all pending/active intents from DB
2. Expire any past-due intents
3. For each remaining intent, check entry criteria
4. Execute position when all criteria pass

Usage:
    scanner = IntentScanner(db=db)
    await scanner.start()
    ...
    await scanner.stop()
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bot.venues.user_context import UserTradingContext
from bot.core.position_manager import PositionManager

logger = logging.getLogger(__name__)


class IntentScanner:
    """
    Scans for position intents and executes when entry criteria pass.

    Lifecycle:
    - pending: just created, scanner picks up on next cycle -> active
    - active: scanner is checking criteria each cycle
    - executed: position opened successfully
    - cancelled: user cancelled
    - expired: past expires_at
    - failed: execution attempted but failed
    """

    SCAN_INTERVAL = 60  # seconds between scans
    MAX_ERRORS_BEFORE_BACKOFF = 5
    BACKOFF_INTERVAL = 180  # seconds to wait after too many errors

    def __init__(self, db):
        self.db = db
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._consecutive_errors = 0

    async def start(self):
        """Start the scanner loop as a background task."""
        if self._running:
            logger.warning("IntentScanner already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("IntentScanner started (interval=%ds)", self.SCAN_INTERVAL)

    async def stop(self):
        """Stop the scanner loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("IntentScanner stopped")

    async def _run_loop(self):
        """Main scanning loop."""
        while self._running:
            try:
                await self._scan_cycle()
                self._consecutive_errors = 0
            except Exception as e:
                self._consecutive_errors += 1
                logger.error(
                    "Scan cycle error (%d consecutive): %s",
                    self._consecutive_errors, e,
                    exc_info=True,
                )

                if self._consecutive_errors >= self.MAX_ERRORS_BEFORE_BACKOFF:
                    logger.warning(
                        "Too many consecutive errors, backing off for %ds",
                        self.BACKOFF_INTERVAL,
                    )
                    await asyncio.sleep(self.BACKOFF_INTERVAL)
                    self._consecutive_errors = 0
                    continue

            await asyncio.sleep(self.SCAN_INTERVAL)

    async def _scan_cycle(self):
        """
        Single scan cycle.

        1. Fetch all scannable intents (pending + active)
        2. Expire any past-due intents
        3. Activate pending intents
        4. Check criteria and execute if ready
        """
        rows = await self.db.fetchall(
            """SELECT * FROM position_intents
               WHERE status IN ('pending', 'active')
               ORDER BY created_at ASC"""
        )

        if not rows:
            logger.debug("No scannable intents")
            return

        logger.info("Scanning %d intents", len(rows))

        now = datetime.utcnow()

        for row in rows:
            try:
                await self._process_intent(row, now)
            except Exception as e:
                logger.error("Error processing intent %s: %s", row["id"], e)

    async def _process_intent(self, row: Dict[str, Any], now: datetime):
        """Process a single intent."""
        intent_id = row["id"]
        user_id = row["user_id"]
        intent_status = row["status"]

        # Check expiry
        if row["expires_at"]:
            expires_at = _parse_datetime(row["expires_at"])
            if expires_at and now > expires_at:
                await self._expire_intent(intent_id)
                return

        # Activate pending intents
        if intent_status == "pending":
            await self.db.execute(
                """UPDATE position_intents
                   SET status = 'active', activated_at = NOW()
                   WHERE id = $1""",
                (intent_id,),
            )
            logger.info("Intent %s activated", intent_id)

        # Check entry criteria
        criteria_result = await self._check_criteria(row)

        # Persist the criteria snapshot regardless of outcome
        await self.db.execute(
            """UPDATE position_intents
               SET criteria_snapshot = $1
               WHERE id = $2""",
            (json.dumps(criteria_result), intent_id),
        )

        if criteria_result["all_passed"]:
            logger.info(
                "All criteria passed for intent %s (user %s), executing...",
                intent_id, user_id,
            )
            await self._execute_intent(row, criteria_result)

    async def _check_criteria(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check all entry criteria for an intent.

        Returns a dict with:
        - all_passed: bool
        - checks: dict of individual check results
        """
        asset = row["asset"]
        checks = {}

        try:
            from bot.venues.hyperliquid.client import HyperliquidClient
            from bot.venues.hyperliquid.funding_oracle import HyperliquidFundingOracle

            client = HyperliquidClient()
            oracle = HyperliquidFundingOracle(client)

            # Check 1: Funding rate
            funding_check = await self._check_funding(oracle, asset, row)
            checks["funding_rate"] = funding_check

            # Check 2: Funding volatility
            volatility_check = await self._check_volatility(oracle, asset, row)
            checks["funding_volatility"] = volatility_check

            # Check 3: Entry price
            price_check = await self._check_price(client, asset, row)
            checks["entry_price"] = price_check

        except Exception as e:
            logger.warning("Failed to check criteria for intent %s: %s", row["id"], e)
            return {
                "all_passed": False,
                "checks": checks,
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat(),
            }

        all_passed = all(c.get("passed", False) for c in checks.values())

        return {
            "all_passed": all_passed,
            "checks": checks,
            "checked_at": datetime.utcnow().isoformat(),
        }

    async def _check_funding(
        self, oracle, asset: str, row: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check if funding rate meets the intent's criteria."""
        try:
            rates = await oracle.get_current_funding_rates()
            rate_info = rates.get(asset)

            if not rate_info:
                return {"passed": False, "reason": f"No funding data for {asset}"}

            current_rate = rate_info.funding_rate if hasattr(rate_info, "funding_rate") else float(rate_info)

            # Funding must be negative (shorts earn)
            if current_rate >= 0:
                return {
                    "passed": False,
                    "reason": "Funding is non-negative (shorts would pay)",
                    "current_rate": current_rate,
                }

            # Check user's minimum funding rate threshold
            min_rate = row.get("min_funding_rate")
            if min_rate is not None and current_rate > min_rate:
                return {
                    "passed": False,
                    "reason": f"Funding rate {current_rate:.6f} above min threshold {min_rate}",
                    "current_rate": current_rate,
                    "min_required": min_rate,
                }

            return {
                "passed": True,
                "current_rate": current_rate,
            }
        except Exception as e:
            return {"passed": False, "reason": f"Funding check error: {e}"}

    async def _check_volatility(
        self, oracle, asset: str, row: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check if funding volatility is within acceptable range."""
        try:
            volatility = await oracle.calculate_funding_volatility(asset)
            max_vol = row.get("max_funding_volatility") or 0.50

            if volatility > max_vol:
                return {
                    "passed": False,
                    "reason": f"Volatility {volatility:.2%} exceeds max {max_vol:.2%}",
                    "current_volatility": volatility,
                    "max_allowed": max_vol,
                }

            return {
                "passed": True,
                "current_volatility": volatility,
            }
        except Exception as e:
            return {"passed": False, "reason": f"Volatility check error: {e}"}

    async def _check_price(
        self, client, asset: str, row: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check if current price is below the max entry price."""
        max_price = row.get("max_entry_price")
        if max_price is None:
            return {"passed": True, "reason": "No price limit set"}

        try:
            mids = await client.get_all_mids()
            current_price = mids.get(asset)

            if current_price is None:
                return {"passed": False, "reason": f"No price data for {asset}"}

            current_price = float(current_price)
            if current_price > max_price:
                return {
                    "passed": False,
                    "reason": f"Price ${current_price:.2f} exceeds max ${max_price:.2f}",
                    "current_price": current_price,
                    "max_price": max_price,
                }

            return {
                "passed": True,
                "current_price": current_price,
            }
        except Exception as e:
            return {"passed": False, "reason": f"Price check error: {e}"}

    async def _execute_intent(self, row: Dict[str, Any], criteria: Dict[str, Any]):
        """Execute the position for an intent that passed all criteria."""
        intent_id = row["id"]
        user_id = row["user_id"]
        asset = row["asset"]
        leverage = row["leverage"]
        size_usd = row["size_usd"]

        try:
            ctx = await UserTradingContext.from_user_id(user_id, self.db)
            async with ctx:
                pm = PositionManager.from_user_context(ctx)
                await pm.__aenter__()
                try:
                    result = await pm.open_position(
                        asset=asset,
                        size_usd=size_usd,
                        leverage=leverage,
                    )
                finally:
                    await pm.__aexit__(None, None, None)

            if result and result.get("success"):
                position_id = result.get("position_id", str(uuid.uuid4()))

                # Persist position and mark intent as executed in a transaction
                async with self.db.transaction() as tx:
                    await tx.execute(
                        """INSERT INTO positions (id, user_id, data, created_at, is_closed)
                           VALUES ($1, $2, $3, NOW(), 0)""",
                        (
                            position_id,
                            user_id,
                            json.dumps({
                                "asset": asset,
                                "leverage": leverage,
                                "size_usd": size_usd,
                                "intent_id": intent_id,
                                "created_at": datetime.utcnow().isoformat(),
                                **{k: v for k, v in result.items() if k != "success"},
                            }),
                        ),
                    )

                    await tx.execute(
                        """UPDATE position_intents
                           SET status = 'executed', position_id = $1,
                               executed_at = NOW(),
                               criteria_snapshot = $2
                           WHERE id = $3""",
                        (position_id, json.dumps(criteria), intent_id),
                    )

                logger.info(
                    "Intent %s executed: position %s opened for user %s",
                    intent_id, position_id, user_id,
                )
            else:
                error = result.get("error", "Unknown error") if result else "No result returned"
                await self._fail_intent(intent_id, error)

        except Exception as e:
            logger.error("Failed to execute intent %s: %s", intent_id, e, exc_info=True)
            await self._fail_intent(intent_id, str(e))

    async def _expire_intent(self, intent_id: str):
        """Mark an intent as expired."""
        await self.db.execute(
            """UPDATE position_intents
               SET status = 'expired'
               WHERE id = $1""",
            (intent_id,),
        )
        logger.info("Intent %s expired", intent_id)

    async def _fail_intent(self, intent_id: str, error: str):
        """Mark an intent as failed."""
        await self.db.execute(
            """UPDATE position_intents
               SET status = 'failed', execution_error = $1
               WHERE id = $2""",
            (error, intent_id),
        )
        logger.warning("Intent %s failed: %s", intent_id, error)


def _parse_datetime(val) -> Optional[datetime]:
    """Parse a datetime string from the database."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None
