"""
Shadow Trading Mode - Paper Trading for Delta Neutral Arbitrage.

This module provides paper trading functionality for testing the strategy
without executing real trades. All intended trades are logged and tracked
with simulated PnL calculations.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from enum import Enum

from src.models.opportunity import ArbitrageOpportunity
from src.models.common import Asset, Protocol, ExitReason
from src.models.funding import FundingRate
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ShadowPositionStatus(str, Enum):
    """Status of a shadow position."""
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass
class ShadowEntry:
    """Record of a shadow entry attempt."""
    timestamp: datetime
    opportunity_id: str
    asset: str
    protocol: str
    leverage: Decimal
    deployed_capital_usd: Decimal
    position_size_usd: Decimal
    expected_funding_apy: Decimal
    expected_net_carry_apy: Decimal
    expected_total_apy: Decimal
    asgard_entry_price: Decimal
    hyperliquid_entry_price: Decimal
    notes: List[str] = field(default_factory=list)


@dataclass
class ShadowExit:
    """Record of a shadow exit."""
    timestamp: datetime
    position_id: str
    reason: str
    asgard_exit_price: Decimal
    hyperliquid_exit_price: Decimal
    funding_pnl: Decimal
    position_pnl: Decimal
    total_pnl: Decimal
    hold_duration_seconds: float
    notes: List[str] = field(default_factory=list)


@dataclass
class ShadowPosition:
    """
    A paper trading position that mirrors a real CombinedPosition.
    
    Tracks the simulated state of a position without executing real trades.
    """
    # Identification
    position_id: str
    opportunity_id: str
    
    # Asset details
    asset: Asset
    protocol: Protocol
    
    # Entry details
    entry_time: datetime
    asgard_entry_price: Decimal
    hyperliquid_entry_price: Decimal
    
    # Position sizing
    deployed_capital_usd: Decimal  # Total capital deployed (both legs)
    per_leg_deployment_usd: Decimal  # Capital per leg
    position_size_usd: Decimal  # Total position size with leverage
    leverage: Decimal
    
    # Expected yields (at entry)
    expected_funding_apy: Decimal
    expected_net_carry_apy: Decimal
    expected_total_apy: Decimal
    
    # Current state
    status: ShadowPositionStatus = ShadowPositionStatus.OPEN
    current_asgard_price: Decimal = field(default=Decimal("0"))
    current_hyperliquid_price: Decimal = field(default=Decimal("0"))
    
    # Performance tracking
    accumulated_funding_pnl: Decimal = field(default=Decimal("0"))
    funding_payments: List[Dict[str, Any]] = field(default_factory=list)
    
    # Exit tracking
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    exit_asgard_price: Optional[Decimal] = None
    exit_hyperliquid_price: Optional[Decimal] = None
    realized_pnl: Optional[Decimal] = None
    
    # History
    entry_record: Optional[ShadowEntry] = None
    exit_record: Optional[ShadowExit] = None
    
    def __post_init__(self):
        """Initialize current prices from entry if not set."""
        if self.current_asgard_price == Decimal("0"):
            self.current_asgard_price = self.asgard_entry_price
        if self.current_hyperliquid_price == Decimal("0"):
            self.current_hyperliquid_price = self.hyperliquid_entry_price
    
    @property
    def is_open(self) -> bool:
        """Check if position is currently open."""
        return self.status == ShadowPositionStatus.OPEN
    
    @property
    def is_closed(self) -> bool:
        """Check if position is closed."""
        return self.status == ShadowPositionStatus.CLOSED
    
    @property
    def long_value_usd(self) -> Decimal:
        """Current long position value (Asgard leg)."""
        # Long position: token amount × current price
        token_amount = self.position_size_usd / self.asgard_entry_price
        return token_amount * self.current_asgard_price
    
    @property
    def short_value_usd(self) -> Decimal:
        """Current short position value (Hyperliquid leg)."""
        # Short position size matches long position size
        return self.position_size_usd
    
    @property
    def delta(self) -> Decimal:
        """Current delta (net exposure)."""
        return self.long_value_usd - self.short_value_usd
    
    @property
    def delta_ratio(self) -> Decimal:
        """Delta as ratio of position size."""
        if self.position_size_usd == 0:
            return Decimal("0")
        return self.delta / self.position_size_usd
    
    @property
    def long_pnl(self) -> Decimal:
        """Unrealized PnL from long leg."""
        # Long profits when price goes up
        price_diff = self.current_asgard_price - self.asgard_entry_price
        token_amount = self.position_size_usd / self.asgard_entry_price
        return price_diff * token_amount
    
    @property
    def short_pnl(self) -> Decimal:
        """Unrealized PnL from short leg."""
        # Short profits when price goes down
        price_diff = self.hyperliquid_entry_price - self.current_hyperliquid_price
        token_amount = self.position_size_usd / self.hyperliquid_entry_price
        return price_diff * token_amount
    
    @property
    def position_pnl(self) -> Decimal:
        """Total position PnL (both legs)."""
        return self.long_pnl + self.short_pnl
    
    @property
    def unrealized_pnl(self) -> Decimal:
        """Total unrealized PnL (position + funding)."""
        return self.position_pnl + self.accumulated_funding_pnl
    
    @property
    def unrealized_pnl_pct(self) -> Decimal:
        """Unrealized PnL as percentage of deployed capital."""
        if self.deployed_capital_usd == 0:
            return Decimal("0")
        return self.unrealized_pnl / self.deployed_capital_usd
    
    @property
    def hold_duration(self) -> Optional[float]:
        """Hold duration in seconds."""
        end_time = self.exit_time or datetime.utcnow()
        return (end_time - self.entry_time).total_seconds()
    
    def update_prices(self, asgard_price: Decimal, hyperliquid_price: Decimal):
        """Update current market prices."""
        self.current_asgard_price = asgard_price
        self.current_hyperliquid_price = hyperliquid_price
    
    def record_funding_payment(self, amount: Decimal, timestamp: Optional[datetime] = None):
        """
        Record a funding payment.
        
        For short positions on Hyperliquid, positive amount = received,
        negative amount = paid.
        """
        self.accumulated_funding_pnl += amount
        self.funding_payments.append({
            "timestamp": timestamp or datetime.utcnow(),
            "amount": amount,
            "cumulative": self.accumulated_funding_pnl,
        })
    
    def close(self, reason: str, asgard_price: Decimal, hyperliquid_price: Decimal,
              exit_time: Optional[datetime] = None):
        """Close the position and calculate realized PnL."""
        self.status = ShadowPositionStatus.CLOSED
        self.exit_time = exit_time or datetime.utcnow()
        self.exit_reason = reason
        self.exit_asgard_price = asgard_price
        self.exit_hyperliquid_price = hyperliquid_price
        
        # Update prices for final calculation
        self.update_prices(asgard_price, hyperliquid_price)
        
        # Calculate realized PnL
        self.realized_pnl = self.unrealized_pnl
        
        logger.info(
            f"Shadow position {self.position_id} closed: {reason}, "
            f"PnL: ${float(self.realized_pnl):,.2f}"
        )


@dataclass
class ShadowPnL:
    """Comprehensive PnL report for shadow trading."""
    
    # Position counts
    total_positions: int = 0
    open_positions: int = 0
    closed_positions: int = 0
    
    # PnL totals
    total_realized_pnl: Decimal = field(default=Decimal("0"))
    total_unrealized_pnl: Decimal = field(default=Decimal("0"))
    total_funding_pnl: Decimal = field(default=Decimal("0"))
    total_position_pnl: Decimal = field(default=Decimal("0"))
    
    # Performance metrics
    winning_trades: int = 0
    losing_trades: int = 0
    
    # Calculated properties
    @property
    def total_pnl(self) -> Decimal:
        """Total PnL (realized + unrealized)."""
        return self.total_realized_pnl + self.total_unrealized_pnl
    
    @property
    def win_rate(self) -> Decimal:
        """Win rate as percentage."""
        total_closed = self.winning_trades + self.losing_trades
        if total_closed == 0:
            return Decimal("0")
        return Decimal(str(self.winning_trades)) / Decimal(str(total_closed))
    
    @property
    def average_pnl_per_trade(self) -> Decimal:
        """Average PnL per closed trade."""
        total_closed = self.winning_trades + self.losing_trades
        if total_closed == 0:
            return Decimal("0")
        return self.total_realized_pnl / Decimal(str(total_closed))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "total_positions": self.total_positions,
            "open_positions": self.open_positions,
            "closed_positions": self.closed_positions,
            "total_realized_pnl": float(self.total_realized_pnl),
            "total_unrealized_pnl": float(self.total_unrealized_pnl),
            "total_pnl": float(self.total_pnl),
            "total_funding_pnl": float(self.total_funding_pnl),
            "total_position_pnl": float(self.total_position_pnl),
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": float(self.win_rate),
            "average_pnl_per_trade": float(self.average_pnl_per_trade),
        }


@dataclass
class ComparisonResult:
    """Result of comparing shadow trades to market performance."""
    
    # Shadow performance
    shadow_total_pnl: Decimal
    shadow_annualized_return: Decimal
    
    # Market benchmark (e.g., HODL)
    market_total_return: Decimal
    market_annualized_return: Decimal
    
    # Comparison
    outperformance: Decimal  # shadow - market
    outperformance_pct: Decimal  # (shadow - market) / |market|
    
    # Risk metrics
    max_drawdown: Decimal
    sharpe_ratio: Optional[Decimal] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "shadow_total_pnl": float(self.shadow_total_pnl),
            "shadow_annualized_return": float(self.shadow_annualized_return),
            "market_total_return": float(self.market_total_return),
            "market_annualized_return": float(self.market_annualized_return),
            "outperformance": float(self.outperformance),
            "outperformance_pct": float(self.outperformance_pct),
            "max_drawdown": float(self.max_drawdown),
            "sharpe_ratio": float(self.sharpe_ratio) if self.sharpe_ratio else None,
        }


class ShadowTrader:
    """
    Paper trading mode for the delta neutral arbitrage strategy.
    
    Logs intended trades without executing them, tracks simulated positions,
    and calculates hypothetical PnL for strategy validation.
    
    Usage:
        trader = ShadowTrader()
        
        # Simulate entry
        position = await trader.shadow_entry(opportunity)
        
        # Update with market data
        trader.update_prices(position_id, new_asgard_price, new_hl_price)
        trader.record_funding_payment(position_id, funding_amount)
        
        # Simulate exit
        await trader.shadow_exit(position, reason="funding_flip")
        
        # Get PnL report
        pnl = await trader.calculate_shadow_pnl()
    """
    
    def __init__(self):
        """Initialize the shadow trader."""
        self._positions: Dict[str, ShadowPosition] = {}
        self._entries: List[ShadowEntry] = []
        self._exits: List[ShadowExit] = []
        self._position_counter: int = 0
        
        logger.info("ShadowTrader initialized - paper trading mode active")
    
    def _generate_position_id(self) -> str:
        """Generate a unique position ID."""
        self._position_counter += 1
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f"shadow_{timestamp}_{self._position_counter:04d}"
    
    async def shadow_entry(self, opportunity: ArbitrageOpportunity) -> ShadowPosition:
        """
        Log a shadow entry for an arbitrage opportunity.
        
        Creates a paper trading position without executing any real trades.
        Records the intended entry with current market prices.
        
        Args:
            opportunity: The arbitrage opportunity to simulate entry for
            
        Returns:
            ShadowPosition: The created paper trading position
        """
        position_id = self._generate_position_id()
        timestamp = datetime.utcnow()
        
        # Calculate per-leg deployment (50/50 split)
        per_leg_deployment = opportunity.deployed_capital_usd / 2
        
        # Get current prices from opportunity context
        # These would typically come from price consensus check
        asgard_price = Decimal("100")  # Placeholder, should be actual price
        hyperliquid_price = Decimal("100")  # Placeholder, should be actual price
        
        # Create entry record
        entry_record = ShadowEntry(
            timestamp=timestamp,
            opportunity_id=opportunity.id,
            asset=opportunity.asset.value,
            protocol=opportunity.selected_protocol.name,
            leverage=opportunity.leverage,
            deployed_capital_usd=opportunity.deployed_capital_usd,
            position_size_usd=opportunity.position_size_usd,
            expected_funding_apy=opportunity.score.funding_apy,
            expected_net_carry_apy=opportunity.score.net_carry_apy,
            expected_total_apy=opportunity.total_expected_apy,
            asgard_entry_price=asgard_price,
            hyperliquid_entry_price=hyperliquid_price,
            notes=["Shadow entry - no real execution"],
        )
        self._entries.append(entry_record)
        
        # Create shadow position
        position = ShadowPosition(
            position_id=position_id,
            opportunity_id=opportunity.id,
            asset=opportunity.asset,
            protocol=opportunity.selected_protocol,
            entry_time=timestamp,
            asgard_entry_price=asgard_price,
            hyperliquid_entry_price=hyperliquid_price,
            deployed_capital_usd=opportunity.deployed_capital_usd,
            per_leg_deployment_usd=per_leg_deployment,
            position_size_usd=opportunity.position_size_usd,
            leverage=opportunity.leverage,
            expected_funding_apy=opportunity.score.funding_apy,
            expected_net_carry_apy=opportunity.score.net_carry_apy,
            expected_total_apy=opportunity.total_expected_apy,
            current_asgard_price=asgard_price,
            current_hyperliquid_price=hyperliquid_price,
            entry_record=entry_record,
        )
        
        self._positions[position_id] = position
        
        logger.info(
            f"Shadow entry: {position_id} - {opportunity.asset.value} @ {float(opportunity.leverage)}x, "
            f"Expected APY: {float(opportunity.total_expected_apy)*100:.2f}%"
        )
        
        return position
    
    async def shadow_exit(self, position: ShadowPosition, reason: str) -> ShadowExit:
        """
        Log a shadow exit for a position.
        
        Closes the paper trading position and calculates realized PnL.
        Does not execute any real trades.
        
        Args:
            position: The shadow position to close
            reason: The reason for exiting (e.g., "funding_flip", "manual")
            
        Returns:
            ShadowExit: The exit record with calculated PnL
        """
        timestamp = datetime.utcnow()
        
        # Get exit prices (in reality, these would be current market prices)
        exit_asgard_price = position.current_asgard_price
        exit_hyperliquid_price = position.current_hyperliquid_price
        
        # Calculate hold duration
        hold_duration = position.hold_duration or 0
        
        # Close the position to calculate realized PnL
        position.close(
            reason=reason,
            asgard_price=exit_asgard_price,
            hyperliquid_price=exit_hyperliquid_price,
            exit_time=timestamp,
        )
        
        # Calculate PnL components
        funding_pnl = position.accumulated_funding_pnl
        position_pnl = position.position_pnl
        total_pnl = position.realized_pnl or Decimal("0")
        
        # Create exit record
        exit_record = ShadowExit(
            timestamp=timestamp,
            position_id=position.position_id,
            reason=reason,
            asgard_exit_price=exit_asgard_price,
            hyperliquid_exit_price=exit_hyperliquid_price,
            funding_pnl=funding_pnl,
            position_pnl=position_pnl,
            total_pnl=total_pnl,
            hold_duration_seconds=hold_duration,
            notes=["Shadow exit - no real execution"],
        )
        self._exits.append(exit_record)
        position.exit_record = exit_record
        
        logger.info(
            f"Shadow exit: {position.position_id} - Reason: {reason}, "
            f"PnL: ${float(total_pnl):,.2f} (Funding: ${float(funding_pnl):,.2f}, "
            f"Position: ${float(position_pnl):,.2f})"
        )
        
        return exit_record
    
    async def calculate_shadow_pnl(self) -> ShadowPnL:
        """
        Calculate comprehensive PnL for all shadow trades.
        
        Aggregates performance across all open and closed positions.
        
        Returns:
            ShadowPnL: Comprehensive PnL report
        """
        pnl = ShadowPnL()
        
        for position in self._positions.values():
            pnl.total_positions += 1
            
            # Funding PnL
            pnl.total_funding_pnl += position.accumulated_funding_pnl
            
            # Position PnL
            pnl.total_position_pnl += position.position_pnl
            
            if position.is_open:
                pnl.open_positions += 1
                pnl.total_unrealized_pnl += position.unrealized_pnl
            else:
                pnl.closed_positions += 1
                realized = position.realized_pnl or Decimal("0")
                pnl.total_realized_pnl += realized
                
                # Track win/loss
                if realized > 0:
                    pnl.winning_trades += 1
                elif realized < 0:
                    pnl.losing_trades += 1
        
        logger.info(
            f"Shadow PnL: Total=${float(pnl.total_pnl):,.2f} "
            f"(Realized=${float(pnl.total_realized_pnl):,.2f}, "
            f"Unrealized=${float(pnl.total_unrealized_pnl):,.2f}), "
            f"Win Rate: {float(pnl.win_rate)*100:.1f}%"
        )
        
        return pnl
    
    async def compare_to_market(self, benchmark_price_start: Decimal,
                                 benchmark_price_end: Decimal,
                                 duration_days: Decimal) -> ComparisonResult:
        """
        Compare shadow trading performance to a market benchmark.
        
        Typically compares to a simple buy-and-hold strategy of the underlying asset.
        
        Args:
            benchmark_price_start: Starting price of benchmark asset
            benchmark_price_end: Ending price of benchmark asset
            duration_days: Duration of the comparison period in days
            
        Returns:
            ComparisonResult: Detailed comparison between shadow and market
        """
        # Calculate shadow performance
        pnl = await self.calculate_shadow_pnl()
        
        # Calculate shadow returns (requires total deployed capital)
        total_deployed = sum(
            pos.deployed_capital_usd for pos in self._positions.values()
        )
        
        if total_deployed > 0:
            shadow_return_pct = pnl.total_pnl / total_deployed
            # Annualize: (1 + r)^(365/d) - 1
            if duration_days > 0:
                shadow_annualized = (
                    (Decimal("1") + shadow_return_pct) ** (Decimal("365") / duration_days) - Decimal("1")
                )
            else:
                shadow_annualized = Decimal("0")
        else:
            shadow_return_pct = Decimal("0")
            shadow_annualized = Decimal("0")
        
        # Calculate market benchmark return (buy and hold)
        if benchmark_price_start > 0:
            market_return_pct = (benchmark_price_end - benchmark_price_start) / benchmark_price_start
            if duration_days > 0:
                market_annualized = (
                    (Decimal("1") + market_return_pct) ** (Decimal("365") / duration_days) - Decimal("1")
                )
            else:
                market_annualized = Decimal("0")
        else:
            market_return_pct = Decimal("0")
            market_annualized = Decimal("0")
        
        # Calculate outperformance
        outperformance = shadow_return_pct - market_return_pct
        if market_return_pct != 0:
            outperformance_pct = outperformance / abs(market_return_pct)
        else:
            outperformance_pct = Decimal("0") if outperformance == 0 else Decimal("inf")
        
        # Calculate max drawdown (simplified)
        max_drawdown = self._calculate_max_drawdown()
        
        result = ComparisonResult(
            shadow_total_pnl=pnl.total_pnl,
            shadow_annualized_return=shadow_annualized,
            market_total_return=market_return_pct,
            market_annualized_return=market_annualized,
            outperformance=outperformance,
            outperformance_pct=outperformance_pct,
            max_drawdown=max_drawdown,
        )
        
        logger.info(
            f"Market comparison: Shadow={float(shadow_return_pct)*100:.2f}%, "
            f"Market={float(market_return_pct)*100:.2f}%, "
            f"Outperformance={float(outperformance)*100:.2f}%"
        )
        
        return result
    
    def _calculate_max_drawdown(self) -> Decimal:
        """Calculate maximum drawdown from position history."""
        max_dd = Decimal("0")
        
        for position in self._positions.values():
            if position.funding_payments:
                # Track cumulative PnL over time
                cumulative = Decimal("0")
                peak = Decimal("0")
                
                for payment in position.funding_payments:
                    cumulative = payment["cumulative"]
                    if cumulative > peak:
                        peak = cumulative
                    
                    drawdown = (peak - cumulative) / peak if peak > 0 else Decimal("0")
                    if drawdown > max_dd:
                        max_dd = drawdown
        
        return max_dd
    
    def get_position(self, position_id: str) -> Optional[ShadowPosition]:
        """Get a shadow position by ID."""
        return self._positions.get(position_id)
    
    def get_open_positions(self) -> List[ShadowPosition]:
        """Get all open shadow positions."""
        return [p for p in self._positions.values() if p.is_open]
    
    def get_closed_positions(self) -> List[ShadowPosition]:
        """Get all closed shadow positions."""
        return [p for p in self._positions.values() if p.is_closed]
    
    def update_prices(self, position_id: str, asgard_price: Decimal, 
                      hyperliquid_price: Decimal):
        """
        Update market prices for a position.
        
        Args:
            position_id: The position ID to update
            asgard_price: Current Asgard price
            hyperliquid_price: Current Hyperliquid price
        """
        position = self._positions.get(position_id)
        if position:
            position.update_prices(asgard_price, hyperliquid_price)
    
    def record_funding_payment(self, position_id: str, amount: Decimal,
                               timestamp: Optional[datetime] = None):
        """
        Record a funding payment for a position.
        
        Args:
            position_id: The position ID
            amount: Funding amount (positive = received, negative = paid)
            timestamp: Optional timestamp for the payment
        """
        position = self._positions.get(position_id)
        if position:
            position.record_funding_payment(amount, timestamp)
            logger.debug(
                f"Shadow funding payment for {position_id}: ${float(amount):,.4f}"
            )
    
    def get_entry_history(self) -> List[ShadowEntry]:
        """Get all shadow entry records."""
        return self._entries.copy()
    
    def get_exit_history(self) -> List[ShadowExit]:
        """Get all shadow exit records."""
        return self._exits.copy()
    
    def reset(self):
        """Reset all shadow trading state."""
        self._positions.clear()
        self._entries.clear()
        self._exits.clear()
        self._position_counter = 0
        logger.info("ShadowTrader state reset")
