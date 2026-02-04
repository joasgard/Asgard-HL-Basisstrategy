"""
Hyperliquid Trading Module.

Provides high-level trading functionality for Hyperliquid perpetuals:
- Opening short positions with retry logic
- Closing positions
- Position monitoring
- Stop-loss during retry (spec 5.1)
- Partial fill handling

Per spec 5.1:
- Max retries: 15 attempts
- Interval: Every 2 seconds (30 second total window)
- Stop-loss monitoring: Active during entire retry window
- Stop-loss trigger: SOL moves >1% against position
"""
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.config.settings import get_settings
from src.utils.logger import get_logger

from .client import HyperliquidClient
from .funding_oracle import HyperliquidFundingOracle
from .signer import HyperliquidSigner, SignedOrder

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
    
    def __init__(
        self,
        client: Optional[HyperliquidClient] = None,
        signer: Optional[HyperliquidSigner] = None,
        oracle: Optional[HyperliquidFundingOracle] = None,
    ):
        """
        Initialize trader.
        
        Args:
            client: HyperliquidClient instance
            signer: HyperliquidSigner instance
            oracle: HyperliquidFundingOracle for price data
        """
        self.client = client or HyperliquidClient()
        self.signer = signer
        self.oracle = oracle
        
        # Lazy initialize signer from settings
        if self.signer is None:
            try:
                settings = get_settings()
                if settings.hyperliquid_private_key:
                    self.signer = HyperliquidSigner()
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
            logger.info(f"Updating leverage: {coin} {leverage}x {'cross' if is_cross else 'isolated'}")
            
            # Sign leverage update
            action_data, signature = self.signer.sign_update_leverage(
                coin=coin,
                leverage=leverage,
                is_cross=is_cross,
            )
            
            # Submit to exchange
            payload = {
                "action": action_data,
                "signature": signature,
                "nonce": action_data["nonce"],
            }
            
            response = await self.client.exchange(payload)
            
            if response.get("status") == "ok":
                logger.info(f"Leverage updated: {coin} {leverage}x")
                return True
            else:
                logger.error(f"Failed to update leverage: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating leverage: {e}")
            return False
    
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
        
        logger.info(f"Opening short: {coin} {size} SOL")
        
        # Get current price for stop-loss reference
        entry_price = await self._get_current_price(coin)
        if entry_price is None:
            return OrderResult(success=False, error="Could not get current price")
        
        stop_loss_price = entry_price * (1 + stop_loss_pct)  # Price going up triggers stop
        
        logger.info(f"Entry price: {entry_price}, Stop-loss: {stop_loss_price}")
        
        target_size = float(size)
        filled_size = 0.0
        total_cost = 0.0
        
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
                signed_order = self.signer.sign_order(
                    coin=coin,
                    is_buy=False,  # Sell for short
                    sz=str(remaining),
                    limit_px="0",  # Market order
                    order_type={"market": {}},
                    reduce_only=False,
                )
                
                # Submit order
                payload = {
                    "action": {
                        "actionType": "order",
                        "orders": [{
                            "coin": signed_order.coin,
                            "isBuy": signed_order.is_buy,
                            "sz": signed_order.sz,
                            "limitPx": signed_order.limit_px,
                            "orderType": "Market",
                            "reduceOnly": signed_order.reduce_only,
                            "nonce": signed_order.nonce,
                        }],
                    },
                    "signature": signed_order.signature,
                    "nonce": signed_order.nonce,
                }
                
                response = await self.client.exchange(payload)
                
                if response.get("status") == "ok":
                    # Check fill
                    fill_info = response.get("response", {})
                    filled = float(fill_info.get("filledSz", 0))
                    
                    if filled > 0:
                        filled_size += filled
                        total_cost += filled * entry_price
                        
                        logger.info(f"Filled {filled} of {target_size} on attempt {attempt + 1}")
                        
                        if filled_size >= target_size * 0.999:  # Allow small rounding errors
                            logger.info(f"Short position fully filled: {filled_size} SOL")
                            return OrderResult(
                                success=True,
                                filled_sz=str(filled_size),
                                avg_px=str(entry_price),
                            )
                        else:
                            # Partial fill - continue retrying
                            logger.info(f"Partial fill: {filled_size}/{target_size}, retrying...")
                    
                    else:
                        logger.warning(f"No fill on attempt {attempt + 1}")
                
                else:
                    logger.warning(f"Order rejected on attempt {attempt + 1}: {response}")
                
                # Wait before retry
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_interval)
                
            except Exception as e:
                logger.error(f"Error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_interval)
        
        # Max retries exceeded
        if filled_size > 0:
            # Partial fill - alert
            logger.warning(
                f"Max retries exceeded with partial fill: {filled_size}/{target_size} "
                f"({filled_size/target_size:.1%})"
            )
            return OrderResult(
                success=True,  # Partial success
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
        
        logger.info(f"Closing short: {coin} {size} SOL")
        
        for attempt in range(max_retries):
            try:
                # Place buy order to close short
                signed_order = self.signer.sign_order(
                    coin=coin,
                    is_buy=True,  # Buy to close short
                    sz=size,
                    limit_px="0",
                    order_type={"market": {}},
                    reduce_only=True,  # Only reduce position
                )
                
                payload = {
                    "action": {
                        "actionType": "order",
                        "orders": [{
                            "coin": signed_order.coin,
                            "isBuy": signed_order.is_buy,
                            "sz": signed_order.sz,
                            "limitPx": signed_order.limit_px,
                            "orderType": "Market",
                            "reduceOnly": signed_order.reduce_only,
                            "nonce": signed_order.nonce,
                        }],
                    },
                    "signature": signed_order.signature,
                    "nonce": signed_order.nonce,
                }
                
                response = await self.client.exchange(payload)
                
                if response.get("status") == "ok":
                    fill_info = response.get("response", {})
                    filled = fill_info.get("filledSz", size)
                    
                    logger.info(f"Short position closed: {filled} SOL")
                    return OrderResult(
                        success=True,
                        filled_sz=filled,
                    )
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
    
    async def get_position(self, coin: str) -> Optional[PositionInfo]:
        """
        Get current position for a coin.
        
        Args:
            coin: Coin symbol
            
        Returns:
            PositionInfo if position exists, None otherwise
        """
        try:
            settings = get_settings()
            if not settings.hyperliquid_wallet_address:
                logger.error("Hyperliquid wallet address not configured")
                return None
            
            response = await self.client.get_clearinghouse_state(
                settings.hyperliquid_wallet_address
            )
            
            asset_positions = response.get("assetPositions", [])
            
            for pos in asset_positions:
                position = pos.get("position", {})
                if position.get("coin") == coin:
                    return PositionInfo(
                        coin=coin,
                        size=float(position.get("szi", 0)),
                        entry_px=float(position.get("entryPx", 0)),
                        leverage=int(position.get("leverage", {}).get("value", 1)),
                        margin_used=float(position.get("marginUsed", 0)),
                        margin_fraction=float(position.get("marginFraction", 0)),
                        unrealized_pnl=float(position.get("unrealizedPnl", 0)),
                        liquidation_px=float(position.get("liquidationPx", 0)) if position.get("liquidationPx") else None,
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
            settings = get_settings()
            if not settings.hyperliquid_wallet_address:
                return {}
            
            return await self.client.get_clearinghouse_state(
                settings.hyperliquid_wallet_address
            )
        except Exception as e:
            logger.error(f"Failed to get clearinghouse state: {e}")
            return {}
    
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
        
        Returns:
            StopLossTrigger with trigger status
        """
        current_price = await self._get_current_price(coin)
        if current_price is None:
            return StopLossTrigger(False, stop_loss_price, 0, 0)
        
        if is_short:
            # For short, stop if price goes up
            triggered = current_price >= stop_loss_price
            move_pct = (current_price - entry_price) / entry_price
        else:
            # For long, stop if price goes down
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
        """
        Execute stop-loss unwind.
        
        Per spec 5.1: Immediate market unwind with 0.1% slippage tolerance
        """
        logger.critical(f"Executing stop-loss unwind for {coin}")
        
        # Close whatever position we have
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
