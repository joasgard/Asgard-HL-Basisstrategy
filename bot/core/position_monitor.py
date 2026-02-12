"""
Multi-tenant Position Monitoring Service.

Continuously monitors all users' open positions and triggers automatic exits
when risk conditions fire. This replaces the single-tenant bot._monitor_cycle()
with a service that works across all users.

Runs every POLL_INTERVAL seconds:
1. Fetch all active positions from DB
2. Group by user
3. For each user, create a UserTradingContext with their wallets
4. Run risk engine checks against live market data
5. Trigger exits if any condition fires (health factor, funding flip, etc.)
6. Update position data in DB with latest PnL, health factor

Usage:
    monitor = PositionMonitorService(db=db)
    await monitor.start()  # Runs in background
    ...
    await monitor.stop()
"""
import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from bot.core.risk_engine import RiskEngine, ExitDecision, ExitReason
from bot.venues.user_context import UserTradingContext

logger = logging.getLogger(__name__)


class PositionMonitorService:
    """
    Multi-tenant position monitoring service.

    Polls the database for all active positions, groups them by user,
    and runs risk engine checks using each user's trading context.
    """

    POLL_INTERVAL = 30  # seconds between monitoring cycles
    MAX_ERRORS_BEFORE_BACKOFF = 5
    BACKOFF_INTERVAL = 120  # seconds to wait after too many errors

    def __init__(self, db, risk_engine: Optional[RiskEngine] = None):
        self.db = db
        self.risk_engine = risk_engine or RiskEngine()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._consecutive_errors = 0

    async def start(self):
        """Start the monitoring loop as a background task."""
        if self._running:
            logger.warning("PositionMonitorService already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("PositionMonitorService started (interval=%ds)", self.POLL_INTERVAL)

    async def stop(self):
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PositionMonitorService stopped")

    async def _run_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._monitor_cycle()
                self._consecutive_errors = 0
            except Exception as e:
                self._consecutive_errors += 1
                logger.error(
                    "Monitor cycle error (%d consecutive): %s",
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

            await asyncio.sleep(self.POLL_INTERVAL)

    async def _monitor_cycle(self):
        """
        Single monitoring cycle.

        1. Query all active positions from DB
        2. Group by user_id
        3. For each user, check their positions against risk engine
        """
        rows = await self.db.fetchall(
            "SELECT id, user_id, data, updated_at FROM positions WHERE is_closed = 0"
        )

        if not rows:
            logger.debug("No active positions to monitor")
            return

        # Group by user
        by_user: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            data = row["data"]
            if isinstance(data, str):
                data = json.loads(data)
            by_user[row["user_id"]].append({
                "position_id": row["id"],
                "data": data,
                "updated_at": row["updated_at"],
            })

        logger.info(
            "Monitoring %d positions across %d users",
            len(rows), len(by_user),
        )

        for user_id, positions in by_user.items():
            try:
                await self._monitor_user_positions(user_id, positions)
            except Exception as e:
                logger.error("Error monitoring user %s: %s", user_id, e)

    async def _monitor_user_positions(
        self,
        user_id: str,
        positions: List[Dict[str, Any]],
    ):
        """
        Monitor all positions for a single user.

        Creates a UserTradingContext for the user, fetches live market data,
        and checks each position against the risk engine.
        """
        ctx = await UserTradingContext.from_user_id(user_id, self.db)

        async with ctx:
            hl_trader = ctx.get_hl_trader()

            try:
                funding_rates = await hl_trader.oracle.get_current_funding_rates()
            except Exception as e:
                logger.warning("Failed to fetch funding rates for user %s: %s", user_id, e)
                funding_rates = {}

            for pos_info in positions:
                try:
                    await self._check_position(
                        ctx=ctx,
                        pos_info=pos_info,
                        funding_rates=funding_rates,
                    )
                except Exception as e:
                    logger.error(
                        "Error checking position %s for user %s: %s",
                        pos_info["position_id"], user_id, e,
                    )

    async def _check_position(
        self,
        ctx: UserTradingContext,
        pos_info: Dict[str, Any],
        funding_rates: Dict,
    ):
        """
        Check a single position against risk conditions.

        Fetches live position data from Hyperliquid, runs risk engine,
        and triggers exit if needed.
        """
        position_id = pos_info["position_id"]
        data = pos_info["data"]
        asset = data.get("asset", "SOL")

        hl_trader = ctx.get_hl_trader()

        # Get live Hyperliquid position data
        hl_position = await hl_trader.get_position(asset)

        # Get Asgard health (if we have a PDA)
        asgard_health = None
        asgard_pda = data.get("asgard_pda")
        if asgard_pda:
            asgard_mgr = ctx.get_asgard_manager()
            try:
                health_status = await asgard_mgr.monitor_health(asgard_pda)
                if health_status:
                    asgard_health = health_status.health_factor
            except Exception as e:
                logger.warning("Failed to check Asgard health for %s: %s", position_id, e)

        # Build position state for risk engine
        current_funding = None
        if asset in funding_rates:
            current_funding = funding_rates[asset]

        # Update position data in DB with latest live data
        updates = {}
        if hl_position:
            updates["hl_unrealized_pnl"] = hl_position.unrealized_pnl
            updates["hl_margin_fraction"] = hl_position.margin_fraction
            updates["hl_liquidation_px"] = hl_position.liquidation_px
        if asgard_health is not None:
            updates["asgard_health_factor"] = asgard_health
        if current_funding is not None:
            funding_val = current_funding.get("funding", 0) if isinstance(current_funding, dict) else current_funding
            updates["current_funding_rate"] = float(funding_val) if funding_val else 0

        if updates:
            merged = {**data, **updates}
            await self.db.execute(
                "UPDATE positions SET data = $1, updated_at = NOW() WHERE id = $2",
                (json.dumps(merged), position_id),
            )

        # Run risk engine checks
        exit_decision = self._evaluate_exit(data, hl_position, asgard_health, current_funding)

        if exit_decision and exit_decision.should_exit:
            logger.warning(
                "Exit trigger fired for position %s (user %s): %s",
                position_id, ctx.user_id, exit_decision.reason.value,
            )
            await self._execute_exit(ctx, position_id, data, exit_decision)

    def _evaluate_exit(
        self,
        data: Dict,
        hl_position,
        asgard_health: Optional[float],
        current_funding,
    ) -> Optional[ExitDecision]:
        """
        Evaluate whether a position should be exited.

        Checks in priority order:
        1. Asgard health factor critical
        2. Hyperliquid margin critical
        3. Funding rate flipped (shorts now paying)
        """
        if asgard_health is not None and asgard_health <= 0.10:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.ASGARD_HEALTH_FACTOR,
                details={"message": f"Health factor critical: {asgard_health:.2%}", "health_factor": asgard_health},
            )

        if hl_position and hl_position.margin_fraction < 0.10:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.HYPERLIQUID_MARGIN,
                details={"message": f"Margin fraction critical: {hl_position.margin_fraction:.2%}", "margin_fraction": hl_position.margin_fraction},
            )

        if current_funding is not None:
            funding_val = current_funding.get("funding", 0) if isinstance(current_funding, dict) else current_funding
            if funding_val and float(funding_val) > 0:
                return ExitDecision(
                    should_exit=True,
                    reason=ExitReason.FUNDING_FLIP,
                    details={"message": f"Funding flipped positive: {float(funding_val):.6f}", "funding_rate": float(funding_val)},
                )

        return None

    async def _execute_exit(
        self,
        ctx: UserTradingContext,
        position_id: str,
        data: Dict,
        exit_decision: ExitDecision,
    ):
        """
        Execute an automatic position exit.

        Closes Hyperliquid short first, then Asgard long.
        Updates position status in DB.
        """
        asset = data.get("asset", "SOL")
        hl_size = data.get("hyperliquid_size", data.get("hl_size"))

        try:
            # Step 1: Close Hyperliquid short first (reduces liquidation risk)
            if hl_size:
                hl_trader = ctx.get_hl_trader()
                close_result = await hl_trader.close_short(asset, str(abs(float(hl_size))))
                if not close_result.success:
                    logger.error(
                        "Failed to close HL short for position %s: %s",
                        position_id, close_result.error,
                    )
                    return

            # Step 2: Close Asgard long
            asgard_pda = data.get("asgard_pda")
            if asgard_pda:
                asgard_mgr = ctx.get_asgard_manager()
                close_result = await asgard_mgr.close_position(asgard_pda)
                if not close_result.success:
                    logger.error(
                        "Failed to close Asgard long for position %s: %s",
                        position_id, close_result.error,
                    )

            # Mark position as closed and archive in a transaction
            async with self.db.transaction() as tx:
                await tx.execute(
                    """UPDATE positions
                       SET is_closed = 1, data = $1, updated_at = NOW()
                       WHERE id = $2""",
                    (json.dumps({
                        **data,
                        "closed_at": datetime.utcnow().isoformat(),
                        "exit_reason": exit_decision.reason.value,
                        "exit_details": exit_decision.details,
                    }), position_id),
                )

                await tx.execute(
                    """INSERT INTO position_history
                       (id, user_id, asset, status, opened_at, closed_at, pnl_usd, funding_earned_usd)
                       VALUES ($1, $2, $3, 'closed', $4, NOW(), $5, $6)""",
                    (
                        position_id,
                        ctx.user_id,
                        asset,
                        data.get("created_at", datetime.utcnow().isoformat()),
                        data.get("total_pnl", 0),
                        data.get("funding_earned", 0),
                    ),
                )

            logger.info(
                "Position %s auto-closed for user %s (reason: %s)",
                position_id, ctx.user_id, exit_decision.reason.value,
            )

        except Exception as e:
            logger.error(
                "Failed to auto-close position %s: %s",
                position_id, e, exc_info=True,
            )
