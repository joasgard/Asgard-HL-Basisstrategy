"""
Autonomous Scanner Service (7.2.1–7.2.5).

Proactively evaluates market opportunities for users with autonomous
trading enabled. Runs alongside (not replacing) the IntentScanner which
handles manually-created intents.

Each scan cycle:
1. Fetch global market data once (funding rates, protocol rates)
2. Query all users with ``enabled = TRUE`` in ``user_strategy_config``
3. For each user (with PG advisory lock per N11):
   a. Check: paused? cooldown? balance? position count?
   b. Evaluate opportunity against user's entry thresholds
   c. Open position if criteria met
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from shared.config.strategy_defaults import (
    SYSTEM_MIN_COOLDOWN_MINUTES,
    SYSTEM_MAX_POSITIONS,
    SYSTEM_MIN_POSITION_USD,
    SYSTEM_MAX_POSITION_USD,
)

logger = logging.getLogger(__name__)


class AutonomousScanner:
    """Evaluates market conditions and opens positions for enabled users."""

    SCAN_INTERVAL = 60  # seconds
    MAX_ERRORS_BEFORE_BACKOFF = 5
    BACKOFF_INTERVAL = 300

    def __init__(self, db, user_risk_manager=None):
        self.db = db
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._consecutive_errors = 0
        self._user_risk_manager = user_risk_manager

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("AutonomousScanner started (interval=%ds)", self.SCAN_INTERVAL)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AutonomousScanner stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self):
        while self._running:
            try:
                await self._scan_cycle()
                self._consecutive_errors = 0
            except Exception as e:
                self._consecutive_errors += 1
                logger.error(
                    "Autonomous scan error (%d consecutive): %s",
                    self._consecutive_errors, e, exc_info=True,
                )
                if self._consecutive_errors >= self.MAX_ERRORS_BEFORE_BACKOFF:
                    logger.warning("Backing off for %ds", self.BACKOFF_INTERVAL)
                    await asyncio.sleep(self.BACKOFF_INTERVAL)
                    self._consecutive_errors = 0
                    continue
            await asyncio.sleep(self.SCAN_INTERVAL)

    async def _scan_cycle(self):
        """Single autonomous scan cycle."""

        # 1. Fetch global market data once
        market_data = await self._fetch_market_data()
        if market_data is None:
            logger.debug("No market data available, skipping cycle")
            return

        # 2. Get all enabled, non-paused users with their strategy configs
        users = await self._get_enabled_users()
        if not users:
            logger.debug("No enabled autonomous users")
            return

        logger.info("Autonomous scan: %d enabled users, evaluating...", len(users))

        # 3. Evaluate each user
        for user_row in users:
            try:
                await self._evaluate_user(user_row, market_data)
            except Exception as e:
                logger.error(
                    "Error evaluating user %s: %s",
                    user_row["user_id"], e,
                )

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def _fetch_market_data(self) -> Optional[Dict[str, Any]]:
        """Fetch global market data for opportunity evaluation."""
        try:
            from bot.venues.hyperliquid.client import HyperliquidClient
            from bot.venues.hyperliquid.funding_oracle import HyperliquidFundingOracle
            from bot.venues.asgard.market_data import AsgardMarketData

            hl_client = HyperliquidClient()
            oracle = HyperliquidFundingOracle(hl_client)
            asgard = AsgardMarketData()

            funding_rates = await oracle.get_current_funding_rates()
            volatilities = {}
            for coin in funding_rates:
                try:
                    volatilities[coin] = await oracle.calculate_funding_volatility(coin)
                except Exception:
                    volatilities[coin] = 1.0  # Default to high volatility

            return {
                "funding_rates": funding_rates,
                "volatilities": volatilities,
                "fetched_at": datetime.utcnow(),
            }
        except Exception as e:
            logger.warning("Failed to fetch market data: %s", e)
            return None

    # ------------------------------------------------------------------
    # User queries
    # ------------------------------------------------------------------

    async def _get_enabled_users(self) -> List[Dict[str, Any]]:
        """Get users with autonomous trading enabled and not paused."""
        return await self.db.fetchall(
            """SELECT sc.user_id, sc.min_carry_apy, sc.min_funding_rate_8hr,
                      sc.max_funding_volatility, sc.max_position_pct,
                      sc.max_concurrent_positions, sc.max_leverage,
                      sc.min_exit_carry_apy, sc.take_profit_pct,
                      sc.stop_loss_pct, sc.auto_reopen, sc.cooldown_minutes,
                      sc.last_close_time, sc.cooldown_at_close, sc.assets
               FROM user_strategy_config sc
               WHERE sc.enabled = TRUE
                 AND sc.paused_at IS NULL"""
        )

    # ------------------------------------------------------------------
    # Per-user evaluation
    # ------------------------------------------------------------------

    async def _evaluate_user(
        self,
        user_row: Dict[str, Any],
        market_data: Dict[str, Any],
    ):
        """Evaluate opportunity for a single user.

        Uses PG advisory lock (N11) to prevent concurrent cycles from
        opening duplicate positions for the same user.
        """
        user_id = user_row["user_id"]

        # 7.2.5: PG advisory lock — if another process is already evaluating
        # this user, skip.
        locked = await self.db.fetchone(
            "SELECT pg_try_advisory_xact_lock(hashtext($1)) AS locked",
            (user_id,),
        )
        if not locked or not locked.get("locked"):
            logger.debug("User %s locked by another process, skipping", user_id)
            return

        # --- Pre-flight checks ---

        # 7.2.2: Cooldown check
        if not self._cooldown_elapsed(user_row):
            logger.debug("User %s still in cooldown", user_id)
            return

        # Check per-user pause in users table (from 6.5)
        user_paused = await self.db.fetchone(
            "SELECT paused_at FROM users WHERE id = $1",
            (user_id,),
        )
        if user_paused and user_paused.get("paused_at"):
            return

        # Check position count
        pos_count_row = await self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM positions WHERE user_id = $1 AND is_closed = 0",
            (user_id,),
        )
        current_positions = pos_count_row["cnt"] if pos_count_row else 0
        max_positions = min(
            user_row.get("max_concurrent_positions", 2),
            SYSTEM_MAX_POSITIONS,
        )
        if current_positions >= max_positions:
            logger.debug(
                "User %s at position limit (%d/%d)", user_id, current_positions, max_positions
            )
            return

        # 7.3.2: Daily trade limit
        if self._user_risk_manager:
            under_limit = await self._user_risk_manager.check_daily_trade_limit(user_id)
            if not under_limit:
                logger.debug("User %s at daily trade limit", user_id)
                return

        # --- Evaluate assets ---
        assets = user_row.get("assets") or ["SOL"]
        funding_rates = market_data.get("funding_rates", {})
        volatilities = market_data.get("volatilities", {})

        for asset in assets:
            rate_info = funding_rates.get(asset)
            if not rate_info:
                continue

            # 7.2.3: Check entry thresholds
            decision = self._check_entry_criteria(user_row, asset, rate_info, volatilities)
            if decision["should_enter"]:
                await self._open_position_for_user(user_id, user_row, asset, decision)
                break  # One position per scan cycle per user

    # ------------------------------------------------------------------
    # Entry criteria (7.2.3)
    # ------------------------------------------------------------------

    def _check_entry_criteria(
        self,
        config: Dict[str, Any],
        asset: str,
        rate_info,
        volatilities: Dict[str, float],
    ) -> Dict[str, Any]:
        """Check if market conditions meet user's entry thresholds.

        Returns dict with ``should_enter`` and details.
        """
        # Extract funding rate
        current_rate_8hr = float(
            rate_info.rate_8hr if hasattr(rate_info, "rate_8hr") else rate_info
        )

        # Funding must be negative (shorts earn)
        if current_rate_8hr >= 0:
            return {"should_enter": False, "reason": "funding_positive"}

        # Min funding rate threshold
        min_rate = config.get("min_funding_rate_8hr", 0.005)
        if abs(current_rate_8hr) < min_rate:
            return {"should_enter": False, "reason": "funding_below_threshold"}

        # Funding volatility
        vol = volatilities.get(asset, 1.0)
        max_vol = config.get("max_funding_volatility", 0.5)
        if vol > max_vol:
            return {"should_enter": False, "reason": "volatility_too_high"}

        # Estimate carry APY (simplified: funding * leverage * 365 * 3)
        # Full carry = funding + lending - borrowing, but funding dominates
        leverage = config.get("max_leverage", 3.0)
        estimated_carry_apy = abs(current_rate_8hr) * 3 * 365 * leverage * 100  # as %

        min_carry = config.get("min_carry_apy", 15.0)
        if estimated_carry_apy < min_carry:
            return {"should_enter": False, "reason": "carry_below_threshold"}

        return {
            "should_enter": True,
            "asset": asset,
            "funding_rate_8hr": current_rate_8hr,
            "estimated_carry_apy": estimated_carry_apy,
            "volatility": vol,
            "leverage": leverage,
        }

    # ------------------------------------------------------------------
    # Cooldown (7.2.2)
    # ------------------------------------------------------------------

    def _cooldown_elapsed(self, config: Dict[str, Any]) -> bool:
        """Check if cooldown period has elapsed since last close.

        Uses ``cooldown_at_close`` (the cooldown value at the time of last close)
        to prevent bypass via config update after close (N6).
        """
        last_close = config.get("last_close_time")
        if last_close is None:
            return True  # Never closed → no cooldown

        if isinstance(last_close, str):
            try:
                last_close = datetime.fromisoformat(last_close)
            except ValueError:
                return True

        # Use the cooldown value that was set when the position was closed
        cooldown_min = config.get("cooldown_at_close")
        if cooldown_min is None:
            cooldown_min = config.get("cooldown_minutes", 30)

        # Enforce system minimum
        cooldown_min = max(cooldown_min, SYSTEM_MIN_COOLDOWN_MINUTES)

        elapsed = datetime.utcnow() - last_close
        return elapsed >= timedelta(minutes=cooldown_min)

    # ------------------------------------------------------------------
    # Position opening
    # ------------------------------------------------------------------

    async def _open_position_for_user(
        self,
        user_id: str,
        config: Dict[str, Any],
        asset: str,
        decision: Dict[str, Any],
    ):
        """Open a position for a user based on the entry decision."""
        try:
            from bot.venues.user_context import UserTradingContext
            from bot.core.position_manager import PositionManager
            from shared.config.assets import Asset
            from shared.models.common import Protocol
            from shared.models.funding import FundingRate, AsgardRates
            from shared.models.opportunity import ArbitrageOpportunity, OpportunityScore

            leverage = Decimal(str(decision["leverage"]))

            # Size based on user's balance * max_position_pct
            ctx = await UserTradingContext.from_user_id(user_id, self.db)
            async with ctx:
                trader = ctx.get_hl_trader()
                balance = await trader.get_withdrawable_balance()

            max_pct = config.get("max_position_pct", 0.25)
            deployed_capital = Decimal(str(balance * max_pct))

            # System caps
            deployed_capital = max(deployed_capital, Decimal(str(SYSTEM_MIN_POSITION_USD)))
            deployed_capital = min(deployed_capital, Decimal(str(SYSTEM_MAX_POSITION_USD)))

            if balance < float(deployed_capital):
                logger.debug(
                    "User %s insufficient balance (%.2f < %.2f)",
                    user_id, balance, float(deployed_capital),
                )
                return

            position_size = deployed_capital * leverage

            current_funding = FundingRate(
                timestamp=datetime.utcnow(),
                coin=asset,
                rate_8hr=Decimal(str(decision["funding_rate_8hr"])),
            )

            asgard_rates = AsgardRates(
                protocol_id=Protocol.MARGINFI.value,
                token_a_mint="",
                token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                token_a_lending_apy=Decimal("0.05"),
                token_b_borrowing_apy=Decimal("0.08"),
                token_b_max_borrow_capacity=position_size * 2,
            )

            opportunity = ArbitrageOpportunity(
                id=f"auto-{user_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                asset=Asset(asset),
                selected_protocol=Protocol.MARGINFI,
                asgard_rates=asgard_rates,
                current_funding=current_funding,
                funding_volatility=Decimal(str(decision.get("volatility", 0.3))),
                leverage=leverage,
                deployed_capital_usd=deployed_capital,
                position_size_usd=position_size,
                score=OpportunityScore(
                    funding_apy=abs(current_funding.rate_annual) * leverage,
                    net_carry_apy=Decimal(str(decision.get("estimated_carry_apy", 0) / 100)),
                ),
                price_deviation=Decimal("0"),
                preflight_checks_passed=True,
            )

            # Execute
            ctx = await UserTradingContext.from_user_id(user_id, self.db)
            async with ctx:
                pm = PositionManager.from_user_context(ctx)
                await pm.__aenter__()
                try:
                    result = await pm.open_position(opportunity=opportunity)
                finally:
                    await pm.__aexit__(None, None, None)

            if result.success and result.position:
                position_id = result.position.position_id

                await self.db.execute(
                    """INSERT INTO positions (id, user_id, data, created_at, is_closed)
                       VALUES ($1, $2, $3, NOW(), 0)""",
                    (
                        position_id,
                        user_id,
                        json.dumps({
                            "asset": asset,
                            "leverage": float(leverage),
                            "size_usd": float(deployed_capital),
                            "source": "autonomous",
                            "created_at": datetime.utcnow().isoformat(),
                        }),
                    ),
                )

                logger.info(
                    "Autonomous position opened: %s for user %s "
                    "(asset=%s, size=$%.0f, leverage=%.1fx)",
                    position_id, user_id, asset,
                    float(deployed_capital), float(leverage),
                )

                # 7.3.2/7.3.3: Record successful trade
                if self._user_risk_manager:
                    await self._user_risk_manager.record_trade(user_id)
            else:
                error = getattr(result, "error", "unknown")
                logger.warning(
                    "Autonomous position failed for user %s: %s",
                    user_id, error,
                )

                # 7.3.3: Record failure for circuit breaker
                if self._user_risk_manager:
                    await self._user_risk_manager.record_failure(
                        user_id, f"open_failed: {error}"
                    )

        except Exception as e:
            logger.error(
                "Failed to open autonomous position for user %s: %s",
                user_id, e, exc_info=True,
            )

            # 7.3.3: Record failure for circuit breaker
            if self._user_risk_manager:
                try:
                    await self._user_risk_manager.record_failure(
                        user_id, f"open_exception: {e}"
                    )
                except Exception:
                    pass
