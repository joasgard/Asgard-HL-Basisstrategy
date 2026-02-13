"""
Hyperliquid Trading Module.

Provides high-level trading functionality for Hyperliquid perpetuals:
- Opening short positions with retry logic
- Closing positions
- Position monitoring
- Stop-loss during retry (spec 5.1)
- Partial fill handling
- Leverage management
- Spot<->perp USDC transfers

Per spec 5.1:
- Max retries: 15 attempts
- Interval: Every 2 seconds (30 second total window)
- Stop-loss monitoring: Active during entire retry window
- Stop-loss trigger: SOL moves >1% against position
"""
import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from shared.config.settings import get_settings
from shared.utils.logger import get_logger

from .client import HyperliquidClient
from .funding_oracle import HyperliquidFundingOracle
from .signer import HyperliquidSigner, SignedAction

logger = get_logger(__name__)


@dataclass
class OrderResult:
    """Result of an order submission."""
    success: bool
    order_id: Optional[str] = None
    filled_sz: Optional[str] = None
    remaining_sz: Optional[str] = None
    avg_px: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PositionInfo:
    """Current position information."""
    coin: str
    size: float  # Positive for long, negative for short
    entry_px: float
    leverage: int
    margin_used: float
    margin_fraction: float
    unrealized_pnl: float
    liquidation_px: Optional[float] = None


@dataclass
class StopLossTrigger:
    """Stop loss trigger information."""
    triggered: bool
    trigger_price: float
    current_price: float
    move_pct: float


class HyperliquidTrader:
    """
    High-level trader for Hyperliquid perpetuals.

    Features:
    - Open/close short positions with retry logic
    - Update leverage
    - Get position info
    - Stop-loss monitoring during retries
    - Partial fill handling
    - Dynamic coin-to-asset-index resolution

    Usage:
        async with HyperliquidTrader() as trader:
            # Open short
            result = await trader.open_short(
                coin="SOL",
                size="10.0",
                max_retries=15,
            )

            # Get position
            position = await trader.get_position("SOL")

            # Close short
            await trader.close_short(coin="SOL", size="10.0")
    """

    # Retry configuration (spec 5.1)
    DEFAULT_MAX_RETRIES = 15
    DEFAULT_RETRY_INTERVAL = 2.0  # seconds
    DEFAULT_STOP_LOSS_PCT = 0.01  # 1%
    MAX_RETRY_WINDOW = 30.0  # seconds

    # Market order slippage: use aggressive price for IOC orders
    MARKET_BUY_SLIPPAGE = 1.02   # 2% above mid
    MARKET_SELL_SLIPPAGE = 0.98  # 2% below mid

    def __init__(
        self,
        client: Optional[HyperliquidClient] = None,
        signer: Optional[HyperliquidSigner] = None,
        oracle: Optional[HyperliquidFundingOracle] = None,
        wallet_address: Optional[str] = None,
        user_id: Optional[str] = None,
        wallet_id: Optional[str] = None,
    ):
        """Initialize trader.

        Args:
            client: HyperliquidClient instance.
            signer: HyperliquidSigner instance (overrides wallet_address if provided).
            oracle: HyperliquidFundingOracle for price data.
            wallet_address: EVM wallet address for this user.
            user_id: User ID for multi-tenant mode.
            wallet_id: Privy wallet ID (from server wallets DB).
        """
        self.client = client or HyperliquidClient()
        self.signer = signer
        self.oracle = oracle
        self.user_id = user_id
        self.wallet_address = wallet_address

        # Cache for coin -> asset index mapping
        self._asset_index_cache: Dict[str, int] = {}

        if self.signer is not None:
            if not self.wallet_address:
                self.wallet_address = self.signer.wallet_address
        elif self.wallet_address:
            try:
                self.signer = HyperliquidSigner(
                    wallet_address=self.wallet_address,
                    user_id=self.user_id,
                    wallet_id=wallet_id,
                )
            except (ValueError, Exception):
                logger.warning("Hyperliquid signer not configured for user wallet")
        else:
            try:
                settings = get_settings()
                if settings.wallet_address and settings.privy_app_id:
                    self.signer = HyperliquidSigner()
                    self.wallet_address = settings.wallet_address
            except ValueError:
                logger.warning("Hyperliquid signer not configured")

    async def __aenter__(self) -> "HyperliquidTrader":
        """Async context manager entry."""
        if not self.client._session or self.client._session.closed:
            await self.client._init_session()
        if self.oracle:
            if not self.oracle.client._session or self.oracle.client._session.closed:
                await self.oracle.client._init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.client.close()
        if self.oracle:
            await self.oracle.client.close()

    # ------------------------------------------------------------------
    # Asset index resolution
    # ------------------------------------------------------------------

    async def _resolve_asset_index(self, coin: str) -> int:
        """
        Resolve coin name to Hyperliquid asset index.

        Queries the API to build the mapping from the universe array.
        Results are cached for the session.

        Args:
            coin: Coin symbol (e.g. "SOL")

        Returns:
            Numeric asset index

        Raises:
            ValueError: If coin not found in universe
        """
        if coin in self._asset_index_cache:
            return self._asset_index_cache[coin]

        response = await self.client.get_meta_and_asset_contexts()
        meta = response[0]
        universe = meta.get("universe", [])

        for i, entry in enumerate(universe):
            name = entry.get("name")
            if name:
                self._asset_index_cache[name] = i

        if coin not in self._asset_index_cache:
            raise ValueError(
                f"Coin {coin} not found in Hyperliquid universe. "
                f"Available: {list(self._asset_index_cache.keys())[:20]}"
            )

        return self._asset_index_cache[coin]

    # ------------------------------------------------------------------
    # Leverage
    # ------------------------------------------------------------------

    async def update_leverage(
        self,
        coin: str,
        leverage: int,
        is_cross: bool = True,
    ) -> bool:
        """
        Update leverage for a coin.

        Args:
            coin: Coin symbol (e.g., "SOL")
            leverage: Leverage value (1-50)
            is_cross: True for cross margin, False for isolated

        Returns:
            True if successful
        """
        if not self.signer:
            logger.error("Signer not configured")
            return False

        try:
            asset_index = await self._resolve_asset_index(coin)

            logger.info(
                f"Updating leverage: {coin} (asset={asset_index}) "
                f"{leverage}x {'cross' if is_cross else 'isolated'}"
            )

            signed = await self.signer.sign_leverage_update(
                asset_index=asset_index,
                leverage=leverage,
                is_cross=is_cross,
            )

            payload = {
                "action": signed.action,
                "nonce": signed.nonce,
                "signature": signed.signature,
            }

            response = await self.client.exchange(payload)

            if response.get("status") == "ok":
                logger.info(f"Leverage updated: {coin} {leverage}x")
                return True
            else:
                error = response.get("response", "Unknown error")
                logger.error(f"Leverage update failed: {error}")
                return False

        except Exception as e:
            logger.error(f"Error updating leverage: {e}")
            return False

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    async def _submit_order(
        self,
        coin: str,
        is_buy: bool,
        sz: str,
        reduce_only: bool = False,
    ) -> dict:
        """
        Build, sign, and submit a market IOC order.

        Args:
            coin: Coin symbol
            is_buy: True for buy, False for sell
            sz: Size as string
            reduce_only: Whether this is a reduce-only order

        Returns:
            API response dict
        """
        asset_index = await self._resolve_asset_index(coin)

        # Get current price for IOC limit price calculation
        current_price = await self._get_current_price(coin)
        if current_price is None:
            raise ValueError(f"Could not get current price for {coin}")

        # IOC at aggressive price acts as market order
        if is_buy:
            limit_px = f"{current_price * self.MARKET_BUY_SLIPPAGE:.1f}"
        else:
            limit_px = f"{current_price * self.MARKET_SELL_SLIPPAGE:.1f}"

        # Market orders use IOC (immediate-or-cancel)
        order_type = {"limit": {"tif": "Ioc"}}

        signed = await self.signer.sign_order(
            asset_index=asset_index,
            is_buy=is_buy,
            sz=sz,
            limit_px=limit_px,
            order_type=order_type,
            reduce_only=reduce_only,
        )

        payload = {
            "action": signed.action,
            "nonce": signed.nonce,
            "signature": signed.signature,
        }

        return await self.client.exchange(payload)

    async def open_short(
        self,
        coin: str,
        size: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_interval: float = DEFAULT_RETRY_INTERVAL,
        stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
    ) -> OrderResult:
        """
        Open a short position with retry logic.

        Per spec 5.1:
        - Max 15 retries every 2 seconds
        - Stop-loss monitoring active during retry window
        - Accept partial fills

        Args:
            coin: Coin symbol (e.g., "SOL")
            size: Position size (e.g., "10.5")
            max_retries: Maximum retry attempts
            retry_interval: Seconds between retries
            stop_loss_pct: Stop loss percentage (default 1%)

        Returns:
            OrderResult with fill details
        """
        if not self.signer:
            return OrderResult(success=False, error="Signer not configured")

        logger.info(f"Opening short: {coin} {size}")

        # Get current price for stop-loss reference
        entry_price = await self._get_current_price(coin)
        if entry_price is None:
            return OrderResult(success=False, error="Could not get current price")

        stop_loss_price = entry_price * (1 + stop_loss_pct)

        logger.info(f"Entry price: {entry_price}, Stop-loss: {stop_loss_price}")

        target_size = float(size)
        filled_size = 0.0

        # Check deposited balance before trading
        deposited_balance = await self.get_deposited_balance()
        required_margin = entry_price * target_size / 3  # Assuming 3x leverage
        if deposited_balance < required_margin * 0.95:
            logger.error(
                f"Insufficient deposited balance: ${deposited_balance:.2f} USDC "
                f"(need ${required_margin:.2f})"
            )
            return OrderResult(
                success=False,
                error=f"Insufficient deposited balance: ${deposited_balance:.2f} USDC",
            )

        for attempt in range(max_retries):
            try:
                # Check stop-loss before each attempt
                stop_check = await self._check_stop_loss(
                    coin=coin,
                    entry_price=entry_price,
                    stop_loss_price=stop_loss_price,
                    is_short=True,
                )

                if stop_check.triggered:
                    logger.critical(
                        f"STOP-LOSS TRIGGERED: {coin} moved {stop_check.move_pct:.2%} "
                        f"against position. Unwinding..."
                    )
                    return await self._execute_stop_loss(
                        coin=coin,
                        target_size=target_size,
                        filled_size=filled_size,
                    )

                # Place sell order (short)
                remaining = target_size - filled_size
                response = await self._submit_order(
                    coin=coin,
                    is_buy=False,
                    sz=f"{remaining:.4f}",
                    reduce_only=False,
                )

                if response.get("status") == "ok":
                    resp_data = response.get("response", {})
                    statuses = resp_data.get("data", {}).get("statuses", [])

                    for s in statuses:
                        if "filled" in s:
                            fill = s["filled"]
                            filled = float(fill.get("totalSz", 0))
                            avg_px = fill.get("avgPx", str(entry_price))
                            if filled > 0:
                                filled_size += filled
                                logger.info(
                                    f"Filled {filled} of {target_size} "
                                    f"@ {avg_px} on attempt {attempt + 1}"
                                )
                        elif "resting" in s:
                            logger.info(f"Order resting (oid={s['resting'].get('oid')})")

                    if filled_size >= target_size * 0.999:
                        logger.info(f"Short position fully filled: {filled_size}")
                        return OrderResult(
                            success=True,
                            filled_sz=str(filled_size),
                            avg_px=str(entry_price),
                        )
                    elif filled_size > 0:
                        logger.info(
                            f"Partial fill: {filled_size}/{target_size}, retrying..."
                        )
                else:
                    error = response.get("response", "Unknown error")
                    logger.warning(f"Order rejected on attempt {attempt + 1}: {error}")

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_interval)

            except Exception as e:
                logger.error(f"Error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_interval)

        # Max retries exceeded
        if filled_size > 0:
            logger.warning(
                f"Max retries exceeded with partial fill: "
                f"{filled_size}/{target_size} ({filled_size / target_size:.1%})"
            )
            return OrderResult(
                success=True,
                filled_sz=str(filled_size),
                remaining_sz=str(target_size - filled_size),
                avg_px=str(entry_price),
                error="Max retries exceeded - partial fill",
            )

        return OrderResult(
            success=False,
            error=f"Failed to fill after {max_retries} attempts",
        )

    async def close_short(
        self,
        coin: str,
        size: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_interval: float = DEFAULT_RETRY_INTERVAL,
    ) -> OrderResult:
        """
        Close a short position (buy to cover).

        Args:
            coin: Coin symbol
            size: Size to close
            max_retries: Maximum retry attempts
            retry_interval: Seconds between retries

        Returns:
            OrderResult with fill details
        """
        if not self.signer:
            return OrderResult(success=False, error="Signer not configured")

        logger.info(f"Closing short: {coin} {size}")

        for attempt in range(max_retries):
            try:
                response = await self._submit_order(
                    coin=coin,
                    is_buy=True,
                    sz=size,
                    reduce_only=True,
                )

                if response.get("status") == "ok":
                    resp_data = response.get("response", {})
                    statuses = resp_data.get("data", {}).get("statuses", [])

                    for s in statuses:
                        if "filled" in s:
                            fill = s["filled"]
                            filled_sz = fill.get("totalSz", size)
                            avg_px = fill.get("avgPx")
                            logger.info(f"Short position closed: {filled_sz}")
                            return OrderResult(
                                success=True,
                                filled_sz=str(filled_sz),
                                avg_px=str(avg_px) if avg_px else None,
                            )

                    logger.warning(f"Close order had no fills: {statuses}")
                else:
                    logger.warning(f"Close order rejected: {response}")

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_interval)

            except Exception as e:
                logger.error(f"Error closing short on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_interval)

        return OrderResult(
            success=False,
            error=f"Failed to close short after {max_retries} attempts",
        )

    # ------------------------------------------------------------------
    # Account state
    # ------------------------------------------------------------------

    async def get_position(self, coin: str) -> Optional[PositionInfo]:
        """
        Get current position for a coin.

        Args:
            coin: Coin symbol

        Returns:
            PositionInfo if position exists, None otherwise
        """
        try:
            wallet = self.wallet_address
            if not wallet:
                logger.error("Hyperliquid wallet address not configured")
                return None

            response = await self.client.get_clearinghouse_state(wallet)

            asset_positions = response.get("assetPositions", [])

            for pos in asset_positions:
                position = pos.get("position", {})
                if position.get("coin") == coin:
                    return PositionInfo(
                        coin=coin,
                        size=float(position.get("szi", 0)),
                        entry_px=float(position.get("entryPx", 0)),
                        leverage=int(
                            position.get("leverage", {}).get("value", 1)
                        ),
                        margin_used=float(position.get("marginUsed", 0)),
                        margin_fraction=float(
                            position.get("marginFraction", 0)
                        ),
                        unrealized_pnl=float(
                            position.get("unrealizedPnl", 0)
                        ),
                        liquidation_px=(
                            float(position.get("liquidationPx", 0))
                            if position.get("liquidationPx")
                            else None
                        ),
                    )

            return None

        except Exception as e:
            logger.error(f"Failed to get position: {e}")
            return None

    async def get_clearinghouse_state(self) -> Dict[str, Any]:
        """
        Get full clearinghouse state.

        Returns:
            Full account state including all positions and balances
        """
        try:
            wallet = self.wallet_address
            if not wallet:
                return {}

            return await self.client.get_clearinghouse_state(wallet)
        except Exception as e:
            logger.error(f"Failed to get clearinghouse state: {e}")
            return {}

    async def get_deposited_balance(self) -> float:
        """
        Get USDC balance deposited in Hyperliquid clearinghouse.

        Returns:
            USDC balance (in whole units, not raw)
        """
        try:
            wallet = self.wallet_address
            if not wallet:
                logger.error("Wallet address not configured")
                return 0.0

            state = await self.client.get_clearinghouse_state(wallet)

            # HL returns crossMarginSummary.accountValue for total equity
            cross_margin = state.get("crossMarginSummary", {})
            account_value = cross_margin.get("accountValue")
            if account_value is not None:
                return float(account_value)

            # Fallback: check withdrawable
            withdrawable = state.get("withdrawable")
            if withdrawable is not None:
                return float(withdrawable)

            return 0.0

        except Exception as e:
            logger.error(f"Failed to get deposited balance: {e}")
            return 0.0

    async def get_withdrawable_balance(self) -> float:
        """
        Get the amount of USDC that can be withdrawn without affecting open positions.

        HL provides ``withdrawable`` in the clearinghouse state which accounts
        for margin requirements of open positions.

        Returns:
            Withdrawable USDC balance (human-readable units).
        """
        try:
            wallet = self.wallet_address
            if not wallet:
                logger.error("Wallet address not configured")
                return 0.0

            state = await self.client.get_clearinghouse_state(wallet)

            # HL directly tells us how much is withdrawable
            withdrawable = state.get("withdrawable")
            if withdrawable is not None:
                return float(withdrawable)

            # If no positions, everything is withdrawable
            cross_margin = state.get("crossMarginSummary", {})
            account_value = cross_margin.get("accountValue")
            total_margin = cross_margin.get("totalMarginUsed")
            if account_value is not None and total_margin is not None:
                return max(0.0, float(account_value) - float(total_margin))

            return 0.0

        except Exception as e:
            logger.error(f"Failed to get withdrawable balance: {e}")
            return 0.0

    # ------------------------------------------------------------------
    # Spot <-> Perp transfers
    # ------------------------------------------------------------------

    async def transfer_spot_to_perp(self, amount_usd: float) -> bool:
        """
        Transfer USDC from HL spot balance to HL perp clearinghouse.

        Uses the usdClassTransfer user-signed action.

        Args:
            amount_usd: Amount of USDC to transfer (e.g., 1000.0)

        Returns:
            True if successful
        """
        if not self.signer:
            logger.error("Signer not configured")
            return False

        try:
            amount_str = f"{amount_usd:.2f}"

            logger.info(
                f"Transferring {amount_usd} USDC from spot to perp on Hyperliquid"
            )

            signed = await self.signer.sign_usd_class_transfer(
                amount=amount_str,
                to_perp=True,
            )

            payload = {
                "action": signed.action,
                "nonce": signed.nonce,
                "signature": signed.signature,
            }

            response = await self.client.exchange(payload)

            if response.get("status") == "ok":
                logger.info(
                    f"Successfully transferred {amount_usd} USDC (spot -> perp)"
                )
                return True
            else:
                error = response.get("response", "Unknown error")
                logger.error(f"Spot transfer failed: {error}")
                return False

        except Exception as e:
            logger.error(f"Error transferring USDC (spot -> perp): {e}")
            return False

    # ------------------------------------------------------------------
    # Price helpers
    # ------------------------------------------------------------------

    async def _get_current_price(self, coin: str) -> Optional[float]:
        """Get current mark price for a coin."""
        try:
            mids = await self.client.get_all_mids()
            price = mids.get(coin)
            return float(price) if price else None
        except Exception as e:
            logger.error(f"Failed to get price for {coin}: {e}")
            return None

    async def _check_stop_loss(
        self,
        coin: str,
        entry_price: float,
        stop_loss_price: float,
        is_short: bool,
    ) -> StopLossTrigger:
        """
        Check if stop-loss should be triggered.

        For short: Stop if price >= stop_loss_price
        """
        current_price = await self._get_current_price(coin)
        if current_price is None:
            return StopLossTrigger(False, stop_loss_price, 0, 0)

        if is_short:
            triggered = current_price >= stop_loss_price
            move_pct = (current_price - entry_price) / entry_price
        else:
            triggered = current_price <= stop_loss_price
            move_pct = (entry_price - current_price) / entry_price

        return StopLossTrigger(
            triggered=triggered,
            trigger_price=stop_loss_price,
            current_price=current_price,
            move_pct=move_pct,
        )

    async def _execute_stop_loss(
        self,
        coin: str,
        target_size: float,
        filled_size: float,
    ) -> OrderResult:
        """Execute stop-loss unwind."""
        logger.critical(f"Executing stop-loss unwind for {coin}")

        if filled_size > 0:
            result = await self.close_short(coin, str(filled_size))
            return OrderResult(
                success=result.success,
                error=f"STOP-LOSS TRIGGERED: {result.error if result.error else ''}",
            )

        return OrderResult(
            success=False,
            error="STOP-LOSS TRIGGERED: No position to unwind",
        )
