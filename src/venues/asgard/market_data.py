"""
Asgard Finance Market Data Module.

This module provides functionality for:
- Fetching and parsing market data from Asgard API
- Calculating net carry APY for different protocols
- Selecting the best protocol for a given position
- Extracting borrowing and lending rates
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.config.assets import Asset, get_mint
from src.config.settings import get_risk_limits
from src.models.common import Protocol
from src.utils.logger import get_logger

from .client import AsgardClient

logger = get_logger(__name__)


@dataclass
class ProtocolRate:
    """Lending and borrowing rates for a specific protocol."""
    protocol: Protocol
    lending_rate: float  # Annual lending rate (e.g., 0.05 = 5%)
    borrowing_rate: float  # Annual borrowing rate (e.g., 0.08 = 8%)
    max_borrow_capacity: float  # Maximum borrow capacity in USD
    token_a_mint: str
    token_b_mint: str
    
    @property
    def protocol_name(self) -> str:
        """Get human-readable protocol name."""
        return self.protocol.name


@dataclass
class NetCarryResult:
    """Result of net carry calculation."""
    protocol: Protocol
    lending_rate: float
    borrowing_rate: float
    net_carry_rate: float  # Net carry on borrowed amount
    net_carry_apy: float  # Net carry on deployed capital
    leverage: float
    has_capacity: bool  # Whether protocol has sufficient borrow capacity


class AsgardMarketData:
    """
    Market data provider for Asgard Finance.
    
    Fetches and analyzes market data to help select the best protocol
    for opening margin positions.
    
    Usage:
        async with AsgardMarketData() as market_data:
            markets = await market_data.get_markets()
            best = await market_data.select_best_protocol(
                asset=Asset.SOL,
                size_usd=50000,
                leverage=3.0
            )
    """
    
    def __init__(self, client: Optional[AsgardClient] = None):
        """
        Initialize market data provider.
        
        Args:
            client: AsgardClient instance. If not provided, creates a new one.
        """
        self.client = client or AsgardClient()
        self._markets_cache: Optional[List[dict]] = None
        self._rates_cache: Optional[Dict[str, List[ProtocolRate]]] = None
    
    async def __aenter__(self) -> "AsgardMarketData":
        """Async context manager entry."""
        if not self.client._session or self.client._session.closed:
            await self.client._init_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.client.close()
    
    async def get_markets(self, use_cache: bool = True) -> List[dict]:
        """
        Fetch all available margin trading strategies/markets.
        
        Args:
            use_cache: If True and cache exists, return cached data.
            
        Returns:
            List of market/strategy data from Asgard API.
            
        Example response item:
            {
                "strategy": "SOL-USDC",
                "protocol": 0,
                "tokenAMint": "So11111111111111111111111111111111111111112",
                "tokenBMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "lendingRate": 0.05,
                "borrowingRate": 0.08,
                "tokenBMaxBorrowCapacity": 1000000
            }
        """
        if use_cache and self._markets_cache is not None:
            return self._markets_cache
        
        try:
            response = await self.client.get_markets()
            markets = response.get("markets", [])
            self._markets_cache = markets
            logger.debug(f"Fetched {len(markets)} markets from Asgard")
            return markets
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            raise
    
    async def get_borrowing_rates(
        self,
        token_a_mint: str,
        use_cache: bool = True,
    ) -> List[ProtocolRate]:
        """
        Get borrowing and lending rates for a specific token across all protocols.
        
        Args:
            token_a_mint: Mint address of the collateral token (e.g., SOL)
            use_cache: If True, use cached market data if available
            
        Returns:
            List of ProtocolRate objects for each protocol supporting this token
        """
        cache_key = token_a_mint
        if use_cache and self._rates_cache and cache_key in self._rates_cache:
            return self._rates_cache[cache_key]
        
        markets = await self.get_markets(use_cache=use_cache)
        rates = []
        
        for market in markets:
            # Match by token_a_mint (collateral token)
            if market.get("tokenAMint") == token_a_mint:
                try:
                    protocol = Protocol(market.get("protocol", 0))
                    rate = ProtocolRate(
                        protocol=protocol,
                        lending_rate=float(market.get("lendingRate", 0)),
                        borrowing_rate=float(market.get("borrowingRate", 0)),
                        max_borrow_capacity=float(market.get("tokenBMaxBorrowCapacity", 0)),
                        token_a_mint=market.get("tokenAMint", ""),
                        token_b_mint=market.get("tokenBMint", ""),
                    )
                    rates.append(rate)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse market data: {e}")
                    continue
        
        # Sort by protocol order (Marginfi > Kamino > Solend > Drift)
        rates.sort(key=lambda r: r.protocol.value)
        
        # Cache results
        if self._rates_cache is None:
            self._rates_cache = {}
        self._rates_cache[cache_key] = rates
        
        logger.debug(f"Found {len(rates)} protocols for token {token_a_mint}")
        return rates
    
    async def calculate_net_carry_apy(
        self,
        protocol: Protocol,
        token_a_mint: str,
        leverage: float = 3.0,
    ) -> Optional[NetCarryResult]:
        """
        Calculate net carry APY for a specific protocol.
        
        Net carry represents the net yield on deployed capital after accounting
        for borrowing costs.
        
        Formula (from spec):
            Net_Carry = (Leverage × Lending_Rate) - ((Leverage - 1) × Borrowing_Rate)
            Net_Carry_APY = Net_Carry / Deployed_Capital
        
        Args:
            protocol: Protocol to calculate for
            token_a_mint: Mint address of collateral token
            leverage: Leverage multiplier (default 3.0x)
            
        Returns:
            NetCarryResult with calculated rates, or None if protocol not available
        """
        rates = await self.get_borrowing_rates(token_a_mint)
        
        # Find the specific protocol
        protocol_rate = next(
            (r for r in rates if r.protocol == protocol),
            None
        )
        
        if protocol_rate is None:
            logger.warning(f"Protocol {protocol.name} not available for token {token_a_mint}")
            return None
        
        # Calculate net carry
        # Lending earns on the full position size (leverage × collateral)
        lending_yield = leverage * protocol_rate.lending_rate
        
        # Borrowing costs on the borrowed amount ((leverage - 1) × collateral)
        borrowing_cost = (leverage - 1) * protocol_rate.borrowing_rate
        
        # Net carry rate (on borrowed amount)
        net_carry_rate = lending_yield - borrowing_cost
        
        # Net carry APY on deployed capital
        # When you deploy $X, you get net_carry_rate return on $X
        net_carry_apy = net_carry_rate
        
        return NetCarryResult(
            protocol=protocol,
            lending_rate=protocol_rate.lending_rate,
            borrowing_rate=protocol_rate.borrowing_rate,
            net_carry_rate=net_carry_rate,
            net_carry_apy=net_carry_apy,
            leverage=leverage,
            has_capacity=True,  # Will be checked separately
        )
    
    async def select_best_protocol(
        self,
        asset: Asset,
        size_usd: float,
        leverage: float = 3.0,
        safety_buffer: float = 1.2,
    ) -> Optional[NetCarryResult]:
        """
        Select the best protocol for opening a position.
        
        Selection criteria (from spec section 6.3):
        1. Filter by tokenAMint (collateral asset)
        2. Check tokenBMaxBorrowCapacity >= size_usd × (leverage-1) × safety_buffer
        3. Calculate net_rate = (leverage × lending) - ((leverage-1) × borrowing)
        4. Return best net carry
        5. Tie-breaker: Marginfi > Kamino > Solend > Drift
        
        Args:
            asset: Asset to use as collateral
            size_usd: Position size in USD
            leverage: Leverage multiplier
            safety_buffer: Safety multiplier for capacity check (default 1.2 = 20% buffer)
            
        Returns:
            NetCarryResult for the best protocol, or None if no suitable protocol found
        """
        from src.config.assets import get_mint
        
        token_a_mint = get_mint(asset)
        if not token_a_mint:
            logger.error(f"Unknown asset: {asset}")
            return None
        
        # Calculate required borrow capacity
        borrow_amount = size_usd * (leverage - 1)
        required_capacity = borrow_amount * safety_buffer
        
        rates = await self.get_borrowing_rates(token_a_mint)
        
        if not rates:
            logger.warning(f"No protocols available for asset {asset.value}")
            return None
        
        best_result: Optional[NetCarryResult] = None
        
        for protocol_rate in rates:
            # Check capacity
            has_capacity = protocol_rate.max_borrow_capacity >= required_capacity
            
            # Calculate net carry
            lending_yield = leverage * protocol_rate.lending_rate
            borrowing_cost = (leverage - 1) * protocol_rate.borrowing_rate
            net_carry_apy = lending_yield - borrowing_cost
            
            result = NetCarryResult(
                protocol=protocol_rate.protocol,
                lending_rate=protocol_rate.lending_rate,
                borrowing_rate=protocol_rate.borrowing_rate,
                net_carry_rate=net_carry_apy,
                net_carry_apy=net_carry_apy,
                leverage=leverage,
                has_capacity=has_capacity,
            )
            
            # Skip if no capacity
            if not has_capacity:
                logger.debug(
                    f"Protocol {result.protocol.name} lacks capacity: "
                    f"{protocol_rate.max_borrow_capacity:.0f} < {required_capacity:.0f}"
                )
                continue
            
            # Compare with current best
            if best_result is None:
                best_result = result
            elif result.net_carry_apy > best_result.net_carry_apy:
                # Better net carry
                best_result = result
            elif result.net_carry_apy == best_result.net_carry_apy:
                # Tie-breaker: prefer lower protocol ID (Marginfi > Kamino > Solend > Drift)
                if result.protocol.value < best_result.protocol.value:
                    best_result = result
        
        if best_result:
            logger.info(
                f"Selected protocol {best_result.protocol.name} for {asset.value} "
                f"with net carry APY: {best_result.net_carry_apy:.2%}"
            )
        else:
            logger.warning(f"No suitable protocol found for {asset.value} with size ${size_usd:,.0f}")
        
        return best_result
    
    def clear_cache(self) -> None:
        """Clear cached market data and rates."""
        self._markets_cache = None
        self._rates_cache = None
        logger.debug("Market data cache cleared")
