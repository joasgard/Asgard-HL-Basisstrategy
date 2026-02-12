"""
Asgard Finance Market Data Module.

This module provides functionality for:
- Fetching and parsing market data from Asgard API
- Calculating net carry APY for different protocols
- Selecting the best protocol for a given position
- Extracting borrowing and lending rates

The Asgard /markets API returns strategies in this shape:
{
  "strategies": {
    "SOL/USDC": {
      "tokenAMint": "So111...",
      "tokenBMint": "EPjF...",
      "liquiditySources": [
        {
          "lendingProtocol": 1,
          "isActive": true,
          "tokenABank": "...",
          "tokenBBank": "...",
          "longMaxLeverage": 3.84,
          "tokenALendingApyRate": 0.045,
          "tokenBBorrowingApyRate": 0.050,
          "tokenBMaxBorrowCapacity": "365619.18",
          ...
        }
      ]
    }
  }
}
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from shared.config.assets import Asset, get_mint
from shared.config.settings import get_risk_limits
from shared.models.common import Protocol
from shared.utils.logger import get_logger

from .client import AsgardClient

logger = get_logger(__name__)

# USDC mint on Solana (Token B for our strategy)
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


@dataclass
class ProtocolRate:
    """Lending and borrowing rates for a specific protocol."""
    protocol: Protocol
    lending_rate: float  # Annual lending rate (e.g., 0.05 = 5%)
    borrowing_rate: float  # Annual borrowing rate (e.g., 0.08 = 8%)
    max_borrow_capacity: float  # Maximum borrow capacity in USD
    token_a_mint: str
    token_b_mint: str
    token_a_bank: str = ""  # Bank address needed for position creation
    token_b_bank: str = ""
    max_leverage: float = 4.0

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
            best = await market_data.select_best_protocol(
                asset=Asset.SOL,
                size_usd=50000,
                leverage=3.0
            )
    """

    def __init__(self, client: Optional[AsgardClient] = None):
        self.client = client or AsgardClient()
        self._strategies_cache: Optional[dict] = None
        self._rates_cache: Optional[Dict[str, List[ProtocolRate]]] = None

    async def __aenter__(self) -> "AsgardMarketData":
        if not self.client._session or self.client._session.closed:
            await self.client._init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.client.close()

    async def close(self) -> None:
        """Close underlying client."""
        await self.client.close()

    async def get_markets(self, use_cache: bool = True) -> dict:
        """
        Fetch raw strategies response from Asgard /markets API.

        Returns the full response dict with "strategies" and "totalStrategies".
        """
        if use_cache and self._strategies_cache is not None:
            return self._strategies_cache

        try:
            response = await self.client.get_markets()
            strategies = response.get("strategies", {})
            self._strategies_cache = response
            logger.debug(f"Fetched {len(strategies)} strategies from Asgard")
            return response
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            raise

    async def get_borrowing_rates(
        self,
        token_a_mint: str,
        use_cache: bool = True,
    ) -> List[ProtocolRate]:
        """
        Get borrowing and lending rates for a specific collateral token
        across all protocols.

        Parses the strategies response to find strategies where tokenAMint
        matches, then extracts rates from each liquiditySource.

        Args:
            token_a_mint: Mint address of the collateral token (e.g., SOL)
            use_cache: If True, use cached data if available

        Returns:
            List of ProtocolRate objects for each protocol supporting this token
        """
        cache_key = token_a_mint
        if use_cache and self._rates_cache and cache_key in self._rates_cache:
            return self._rates_cache[cache_key]

        response = await self.get_markets(use_cache=use_cache)
        strategies = response.get("strategies", {})
        rates = []

        for strategy_name, strategy in strategies.items():
            # Match by tokenAMint and ensure tokenB is USDC
            if strategy.get("tokenAMint") != token_a_mint:
                continue
            if strategy.get("tokenBMint") != USDC_MINT:
                continue

            # Parse each liquidity source within this strategy
            for source in strategy.get("liquiditySources", []):
                if not source.get("isActive", False):
                    continue

                try:
                    protocol = Protocol(source.get("lendingProtocol", -1))
                except ValueError:
                    logger.warning(f"Unknown protocol ID: {source.get('lendingProtocol')}")
                    continue

                # Parse rates (API returns decimals, e.g., 0.05 = 5%)
                lending_rate = float(source.get("tokenALendingApyRate", 0))
                borrowing_rate = float(source.get("tokenBBorrowingApyRate", 0))

                # Capacity is returned as string
                try:
                    max_borrow_capacity = float(source.get("tokenBMaxBorrowCapacity", "0"))
                except (ValueError, TypeError):
                    max_borrow_capacity = 0.0

                max_leverage = float(source.get("longMaxLeverage", 4.0))

                rate = ProtocolRate(
                    protocol=protocol,
                    lending_rate=lending_rate,
                    borrowing_rate=borrowing_rate,
                    max_borrow_capacity=max_borrow_capacity,
                    token_a_mint=strategy.get("tokenAMint", ""),
                    token_b_mint=strategy.get("tokenBMint", ""),
                    token_a_bank=source.get("tokenABank", ""),
                    token_b_bank=source.get("tokenBBank", ""),
                    max_leverage=max_leverage,
                )
                rates.append(rate)

                logger.debug(
                    f"  {strategy_name} via {protocol.name}: "
                    f"lend={lending_rate:.4f} borrow={borrowing_rate:.4f} "
                    f"cap=${max_borrow_capacity:,.0f} maxLev={max_leverage:.1f}x"
                )

        # Sort by protocol order (Marginfi > Kamino > Solend > Drift)
        rates.sort(key=lambda r: r.protocol.value)

        # Cache results
        if self._rates_cache is None:
            self._rates_cache = {}
        self._rates_cache[cache_key] = rates

        logger.debug(f"Found {len(rates)} protocols for token {token_a_mint[:10]}...")
        return rates

    async def calculate_net_carry_apy(
        self,
        protocol: Protocol,
        token_a_mint: str,
        leverage: float = 3.0,
    ) -> Optional[NetCarryResult]:
        """
        Calculate net carry APY for a specific protocol.

        Formula:
            Net_Carry = (Leverage x Lending_Rate) - ((Leverage - 1) x Borrowing_Rate)

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
            logger.warning(f"Protocol {protocol.name} not available for token {token_a_mint[:10]}...")
            return None

        lending_yield = leverage * protocol_rate.lending_rate
        borrowing_cost = (leverage - 1) * protocol_rate.borrowing_rate
        net_carry_rate = lending_yield - borrowing_cost
        net_carry_apy = net_carry_rate

        return NetCarryResult(
            protocol=protocol,
            lending_rate=protocol_rate.lending_rate,
            borrowing_rate=protocol_rate.borrowing_rate,
            net_carry_rate=net_carry_rate,
            net_carry_apy=net_carry_apy,
            leverage=leverage,
            has_capacity=True,
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

        Selection criteria:
        1. Filter by tokenAMint (collateral asset) + tokenBMint (USDC)
        2. Check tokenBMaxBorrowCapacity >= size_usd x (leverage-1) x safety_buffer
        3. Check longMaxLeverage >= requested leverage
        4. Calculate net_rate = (leverage x lending) - ((leverage-1) x borrowing)
        5. Return best net carry
        6. Tie-breaker: lower protocol ID wins (Marginfi > Kamino > Solend > Drift)

        Args:
            asset: Asset to use as collateral
            size_usd: Position size in USD
            leverage: Leverage multiplier
            safety_buffer: Safety multiplier for capacity check (default 1.2 = 20% buffer)

        Returns:
            NetCarryResult for the best protocol, or None if no suitable protocol found
        """
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

            # Check max leverage supports our requested leverage
            if protocol_rate.max_leverage < leverage:
                logger.debug(
                    f"Protocol {protocol_rate.protocol.name} max leverage "
                    f"{protocol_rate.max_leverage:.1f}x < requested {leverage:.1f}x"
                )
                continue

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
                    f"${protocol_rate.max_borrow_capacity:,.0f} < ${required_capacity:,.0f}"
                )
                continue

            # Compare with current best
            if best_result is None:
                best_result = result
            elif result.net_carry_apy > best_result.net_carry_apy:
                best_result = result
            elif result.net_carry_apy == best_result.net_carry_apy:
                if result.protocol.value < best_result.protocol.value:
                    best_result = result

        if best_result:
            logger.info(
                f"Selected protocol {best_result.protocol.name} for {asset.value}: "
                f"net carry APY={best_result.net_carry_apy:.2%}, "
                f"lend={best_result.lending_rate:.2%}, borrow={best_result.borrowing_rate:.2%}"
            )
        else:
            logger.warning(f"No suitable protocol found for {asset.value} with size ${size_usd:,.0f}")

        return best_result

    def clear_cache(self) -> None:
        """Clear cached market data and rates."""
        self._strategies_cache = None
        self._rates_cache = None
        logger.debug("Market data cache cleared")
