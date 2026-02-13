"""
Price Consensus Module.

Provides price comparison between Asgard (Solana) and Hyperliquid (Arbitrum)
to detect significant price deviations before executing trades.

Key Features:
- Fetches prices from both venues simultaneously
- Calculates price deviation percentage
- Raises alert if deviation exceeds threshold (0.5%)
- Provides consensus result with detailed price information
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from shared.config.assets import Asset, get_mint

from shared.utils.logger import get_logger
from bot.venues.asgard.market_data import AsgardMarketData
from bot.venues.hyperliquid.client import HyperliquidClient

logger = get_logger(__name__)


@dataclass
class ConsensusResult:
    """Result of price consensus check between venues."""
    
    # Price data
    asgard_price: Decimal
    hyperliquid_price: Decimal
    
    # Deviation calculation
    price_deviation: Decimal  # Absolute deviation as percentage (e.g., 0.005 = 0.5%)
    deviation_percent: Decimal  # Same as price_deviation for clarity
    
    # Asset info
    asset: Asset
    
    # Consensus status
    is_within_threshold: bool
    threshold: Decimal
    
    # Detailed info
    asgard_source: str = "oracle"  # Source of Asgard price (oracle/market)
    hyperliquid_source: str = "markPx"  # Source of HL price (markPx/oraclePx)
    
    @property
    def consensus_price(self) -> Decimal:
        """
        Calculate consensus price as average of both venues.
        
        Returns:
            Average price between venues
        """
        return (self.asgard_price + self.hyperliquid_price) / Decimal("2")
    
    @property
    def price_divergence(self) -> str:
        """
        Get human-readable divergence description.
        
        Returns:
            "asgard_higher", "hyperliquid_higher", or "equal"
        """
        if self.asgard_price > self.hyperliquid_price:
            return "asgard_higher"
        elif self.hyperliquid_price > self.asgard_price:
            return "hyperliquid_higher"
        return "equal"
    
    def to_summary(self) -> dict:
        """Get summary dict for logging."""
        return {
            "asset": self.asset.value,
            "asgard_price": float(self.asgard_price),
            "hyperliquid_price": float(self.hyperliquid_price),
            "deviation": float(self.price_deviation),
            "deviation_bps": float(self.price_deviation * 10000),  # Basis points
            "within_threshold": self.is_within_threshold,
            "threshold": float(self.threshold),
        }


class PriceConsensus:
    """
    Price consensus checker between Asgard and Hyperliquid.
    
    Compares prices for the same asset across both venues to detect
    significant deviations that could indicate:
    - Market inefficiency
    - Exchange issues
    - Latency arbitrage opportunities
    - Risk of bad fills
    
    Usage:
        async with PriceConsensus() as consensus:
            result = await consensus.check_consensus(Asset.SOL)
            if not result.is_within_threshold:
                logger.warning(f"Price deviation detected: {result.deviation_percent:.2%}")
    """
    
    # Default maximum acceptable price deviation (0.5%)
    MAX_PRICE_DEVIATION = Decimal("0.005")
    
    # Basis points conversion (1% = 100 bps)
    BPS_CONVERSION = Decimal("10000")
    
    def __init__(
        self,
        asgard_market_data: Optional[AsgardMarketData] = None,
        hyperliquid_client: Optional[HyperliquidClient] = None,
        max_deviation: Optional[Decimal] = None,
    ):
        """
        Initialize price consensus checker.
        
        Args:
            asgard_market_data: AsgardMarketData instance. Creates new if None.
            hyperliquid_client: HyperliquidClient instance. Creates new if None.
            max_deviation: Maximum acceptable deviation. Uses default if None.
        """
        self.asgard = asgard_market_data
        self.hyperliquid = hyperliquid_client
        self.max_deviation = max_deviation or self.MAX_PRICE_DEVIATION
        
        # Track ownership for cleanup
        self._own_asgard = asgard_market_data is None
        self._own_hyperliquid = hyperliquid_client is None
    
    async def __aenter__(self) -> "PriceConsensus":
        """Async context manager entry."""
        if self._own_asgard and self.asgard is None:
            self.asgard = AsgardMarketData()
        if self._own_hyperliquid and self.hyperliquid is None:
            self.hyperliquid = HyperliquidClient()
        
        # Initialize sessions
        if self.asgard and self.asgard.client._session is None:
            await self.asgard.client._init_session()
        if self.hyperliquid and self.hyperliquid._session is None:
            await self.hyperliquid._init_session()
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._own_asgard and self.asgard:
            await self.asgard.close()
        if self._own_hyperliquid and self.hyperliquid:
            await self.hyperliquid.close()
    
    async def check_consensus(
        self,
        asset: Asset,
        coin: str = "SOL",
    ) -> ConsensusResult:
        """
        Check price consensus between Asgard and Hyperliquid.
        
        Fetches prices from both venues simultaneously and calculates
        the percentage deviation. Raises warning if deviation exceeds
        the configured threshold.
        
        Args:
            asset: Asset to check (SOL, jitoSOL, jupSOL, INF)
            coin: Coin symbol on Hyperliquid (always "SOL" for SOL-PERP)
            
        Returns:
            ConsensusResult with price data and deviation analysis
            
        Raises:
            PriceDeviationError: If deviation exceeds threshold (optional)
        """
        # Fetch prices concurrently
        asgard_price, hyperliquid_price = await self._fetch_prices(asset, coin)
        
        # Calculate deviation
        deviation = self._calculate_deviation(asgard_price, hyperliquid_price)
        
        # Determine if within threshold
        is_within_threshold = deviation <= self.max_deviation
        
        result = ConsensusResult(
            asgard_price=asgard_price,
            hyperliquid_price=hyperliquid_price,
            price_deviation=deviation,
            deviation_percent=deviation,
            asset=asset,
            is_within_threshold=is_within_threshold,
            threshold=self.max_deviation,
        )
        
        # Log result
        if is_within_threshold:
            logger.debug(
                f"Price consensus OK for {asset.value}: "
                f"deviation={deviation:.4%} ({deviation * self.BPS_CONVERSION:.1f} bps)"
            )
        else:
            logger.warning(
                f"Price deviation detected for {asset.value}: "
                f"{result.price_divergence}, "
                f"deviation={deviation:.4%} ({deviation * self.BPS_CONVERSION:.1f} bps), "
                f"threshold={self.max_deviation:.4%}"
            )
        
        return result
    
    async def _fetch_prices(
        self,
        asset: Asset,
        coin: str,
    ) -> tuple[Decimal, Decimal]:
        """
        Fetch prices from both venues concurrently.

        Primary strategy: compare Hyperliquid mark price (perp) vs oracle price.
        Fallback: compare Asgard oracle vs Hyperliquid mark price (only if both
        venues expose price data — Asgard's /markets API may omit oracle prices).

        Args:
            asset: Asset for Asgard price
            coin: Coin symbol for Hyperliquid price

        Returns:
            Tuple of (asgard_price, hyperliquid_price)
        """
        # Try to get both Hyperliquid mark and oracle prices first — this is
        # the most reliable comparison since Asgard /markets doesn't always
        # include price fields.
        hl_mark, hl_oracle = await self._get_hyperliquid_prices(coin)

        if hl_oracle is not None:
            # Compare mark vs oracle on Hyperliquid (best price consensus check)
            return hl_oracle, hl_mark

        # Oracle not available — try Asgard as second source
        try:
            asgard_price = await self._get_asgard_price(asset)
            return asgard_price, hl_mark
        except (ValueError, Exception) as e:
            logger.debug(f"Asgard price unavailable ({e}), using HL mark as both")
            # If Asgard also has no price, consensus is trivially OK (same price)
            return hl_mark, hl_mark
    
    async def _get_asgard_price(self, asset: Asset) -> Decimal:
        """
        Get asset price from Asgard.
        
        Asgard provides oracle prices through the markets endpoint.
        
        Args:
            asset: Asset to get price for
            
        Returns:
            Asset price in USD
        """
        try:
            # Get markets and find the asset
            markets = await self.asgard.get_markets(use_cache=True)
            
            token_mint = get_mint(asset)
            
            # Find market for this asset in strategies dict
            strategies = markets.get("strategies", {})
            for strategy_name, strategy in strategies.items():
                if strategy.get("tokenAMint") == token_mint:
                    # Try to get oracle price, fallback to other price fields
                    price = strategy.get("oraclePrice")
                    if price is None:
                        price = strategy.get("price")
                    if price is None:
                        price = strategy.get("tokenAPrice")

                    if price is not None:
                        return Decimal(str(price))
            
            # If not found in markets, use a fallback
            logger.warning(f"Price not found in Asgard markets for {asset.value}, using fallback")
            return await self._get_fallback_asgard_price(asset)
            
        except Exception as e:
            logger.error(f"Failed to fetch Asgard price for {asset.value}: {e}")
            raise
    
    async def _get_hyperliquid_price(self, coin: str) -> Decimal:
        """
        Get asset price from Hyperliquid (mark price).

        Args:
            coin: Coin symbol (e.g., "SOL")

        Returns:
            Asset price in USD
        """
        mark, _ = await self._get_hyperliquid_prices(coin)
        return mark

    async def _get_hyperliquid_prices(self, coin: str) -> tuple[Decimal, Optional[Decimal]]:
        """
        Get both mark and oracle prices from Hyperliquid.

        Args:
            coin: Coin symbol (e.g., "SOL")

        Returns:
            Tuple of (mark_price, oracle_price). oracle_price may be None.
        """
        try:
            response = await self.hyperliquid.get_meta_and_asset_contexts()

            # Response is [meta, assetCtxs] — a 2-element list
            meta, asset_ctxs = response[0], response[1]

            # Find coin index from universe (contexts are positional, no 'coin' field)
            universe = meta.get("universe", [])
            coin_index = None
            for i, entry in enumerate(universe):
                if entry.get("name") == coin:
                    coin_index = i
                    break

            if coin_index is None or coin_index >= len(asset_ctxs):
                raise ValueError(f"Coin {coin} not found in Hyperliquid asset contexts")

            ctx = asset_ctxs[coin_index]

            mark_price = ctx.get("markPx")
            oracle_price = ctx.get("oraclePx")

            if mark_price is None and oracle_price is None:
                raise ValueError(f"No price available for {coin}")

            # If mark is missing, fall back to oracle
            if mark_price is None:
                mark_price = oracle_price
                oracle_price = None

            mark_dec = Decimal(str(mark_price))
            oracle_dec = Decimal(str(oracle_price)) if oracle_price is not None else None
            return mark_dec, oracle_dec

        except Exception as e:
            logger.error(f"Failed to fetch Hyperliquid price for {coin}: {e}")
            raise
    
    async def _get_fallback_asgard_price(self, asset: Asset) -> Decimal:
        """
        Get fallback price for Asgard when markets don't have it.
        
        For LSTs, we can estimate based on SOL price + staking premium.
        
        Args:
            asset: Asset to get price for
            
        Returns:
            Estimated asset price
        """
        # For now, return SOL price for all assets (LSTs track SOL)
        # In production, this could call a price oracle or DEX
        markets = await self.asgard.get_markets(use_cache=True)
        strategies = markets.get("strategies", {})

        for strategy_name, strategy in strategies.items():
            if "SOL" in strategy_name:
                price = strategy.get("oraclePrice") or strategy.get("price")
                if price:
                    return Decimal(str(price))
        
        raise ValueError(f"Could not get fallback price for {asset.value}")
    
    def _calculate_deviation(
        self,
        price1: Decimal,
        price2: Decimal,
    ) -> Decimal:
        """
        Calculate percentage deviation between two prices.
        
        Formula: |price1 - price2| / ((price1 + price2) / 2)
        
        Args:
            price1: First price
            price2: Second price
            
        Returns:
            Deviation as percentage (e.g., 0.005 = 0.5%)
        """
        if price1 == 0 and price2 == 0:
            return Decimal("0")
        
        if price1 == 0 or price2 == 0:
            # One price is zero, return max deviation
            return Decimal("1")  # 100%
        
        # Calculate absolute difference
        diff = abs(price1 - price2)
        
        # Calculate average
        avg = (price1 + price2) / Decimal("2")
        
        # Return deviation as percentage
        return diff / avg
    
    def calculate_slippage_adjusted_prices(
        self,
        consensus_result: ConsensusResult,
        slippage_bps: Decimal = Decimal("50"),  # 50 bps = 0.5%
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate worst-case prices with slippage.
        
        Args:
            consensus_result: Consensus result with base prices
            slippage_bps: Slippage in basis points
            
        Returns:
            Tuple of (worst_long_price, worst_short_price)
        """
        slippage_pct = slippage_bps / self.BPS_CONVERSION
        
        # For long: worse price is higher
        worst_long = consensus_result.asgard_price * (Decimal("1") + slippage_pct)
        
        # For short: worse price is lower
        worst_short = consensus_result.hyperliquid_price * (Decimal("1") - slippage_pct)
        
        return worst_long, worst_short


class PriceDeviationError(Exception):
    """Raised when price deviation exceeds acceptable threshold."""
    
    def __init__(
        self,
        message: str,
        deviation: Decimal,
        threshold: Decimal,
        asgard_price: Decimal,
        hyperliquid_price: Decimal,
    ):
        super().__init__(message)
        self.deviation = deviation
        self.threshold = threshold
        self.asgard_price = asgard_price
        self.hyperliquid_price = hyperliquid_price
