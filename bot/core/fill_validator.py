"""
Fill Validation Module.

Validates execution fills and implements "soft stop" logic for the
delta neutral arbitrage strategy.

Key Features:
- Validates fills against expected prices
- Calculates actual execution slippage
- Implements soft stop logic for deviation > 0.5%
- Re-evaluates profitability at actual fill prices
- Prevents closing profitable positions during volatility

Soft Stop Logic (spec 5.1.3):
- Hard deviation check of 0.5% triggers profitability re-evaluation
- Position only unwound if total expected APY < 0 at actual prices
- Prevents closing profitable positions during volatile but viable conditions
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from shared.config.assets import Asset
from shared.models.opportunity import ArbitrageOpportunity, OpportunityScore
from shared.utils.logger import get_logger

from .price_consensus import ConsensusResult

logger = get_logger(__name__)


@dataclass
class FillInfo:
    """Information about a single leg fill."""
    
    # Fill details
    venue: str  # "asgard" or "hyperliquid"
    side: str  # "long" or "short"
    size_usd: Decimal
    filled_price: Decimal
    expected_price: Decimal
    
    # Optional
    slippage_bps: Optional[Decimal] = None
    fees_usd: Optional[Decimal] = None
    
    def __post_init__(self):
        """Calculate slippage if not provided."""
        if self.slippage_bps is None and self.expected_price > 0:
            # Calculate slippage in basis points
            price_diff = abs(self.filled_price - self.expected_price)
            slippage = price_diff / self.expected_price * Decimal("10000")
            self.slippage_bps = slippage


@dataclass
class PositionReference:
    """
    Reference prices for position entry.
    
    Captures the expected prices at entry for later comparison
    with actual fills.
    """
    asgard_entry_price: Decimal
    hyperliquid_entry_price: Decimal
    max_acceptable_deviation: Decimal = Decimal("0.005")  # 0.5%
    
    # Optional: track timing
    timestamp: Optional[str] = None
    
    @property
    def price_spread(self) -> Decimal:
        """Calculate price spread between venues."""
        return abs(self.asgard_entry_price - self.hyperliquid_entry_price)
    
    @property
    def avg_price(self) -> Decimal:
        """Calculate average entry price."""
        return (self.asgard_entry_price + self.hyperliquid_entry_price) / Decimal("2")


@dataclass
class ValidationResult:
    """Result of fill validation."""
    
    # Validation status
    is_valid: bool
    action: str  # "proceed", "soft_stop", "hard_stop"
    
    # Fill details
    asgard_fill: Optional[FillInfo] = None
    hyperliquid_fill: Optional[FillInfo] = None
    
    # Deviation analysis
    asgard_deviation: Decimal = Decimal("0")
    hyperliquid_deviation: Decimal = Decimal("0")
    max_deviation: Decimal = Decimal("0")
    
    # Profitability at fills
    opportunity_at_entry: Optional[ArbitrageOpportunity] = None
    opportunity_at_fills: Optional[ArbitrageOpportunity] = None
    apy_at_fills: Decimal = Decimal("0")
    
    # Soft stop details
    soft_stop_triggered: bool = False
    soft_stop_reason: Optional[str] = None
    should_unwind: bool = False
    
    # Diagnostics
    notes: list = field(default_factory=list)
    
    def to_summary(self) -> dict:
        """Get summary dict for logging."""
        return {
            "is_valid": self.is_valid,
            "action": self.action,
            "max_deviation": float(self.max_deviation),
            "max_deviation_bps": float(self.max_deviation * 10000),
            "apy_at_fills": float(self.apy_at_fills),
            "soft_stop_triggered": self.soft_stop_triggered,
            "should_unwind": self.should_unwind,
            "notes": self.notes,
        }


class FillValidator:
    """
    Validator for execution fills with soft stop logic.
    
    Validates that executed fills are within acceptable deviation
    from expected prices. Implements the "soft stop" logic where
    positions are only unwound if they become unprofitable.
    
    Usage:
        validator = FillValidator()
        
        # After execution
        result = await validator.validate_fills(
            asgard_fill=asgard_fill_info,
            hyperliquid_fill=hl_fill_info,
            expected_spread=expected_spread,
            opportunity=original_opportunity,
        )
        
        if result.action == "soft_stop":
            if result.should_unwind:
                await close_position()
            else:
                logger.info("Soft stop: position still profitable, holding")
    """
    
    # Maximum acceptable fill deviation (0.5%)
    MAX_FILL_DEVIATION = Decimal("0.005")
    
    # Basis points conversion
    BPS = Decimal("10000")
    
    def __init__(self, max_deviation: Optional[Decimal] = None):
        """
        Initialize fill validator.
        
        Args:
            max_deviation: Maximum acceptable deviation. Uses default if None.
        """
        self.max_deviation = max_deviation or self.MAX_FILL_DEVIATION
    
    async def validate_fills(
        self,
        asgard_fill: FillInfo,
        hyperliquid_fill: FillInfo,
        expected_spread: Decimal,  # noqa: F841 - Reserved for future use
        opportunity: ArbitrageOpportunity,
    ) -> ValidationResult:
        """
        Validate execution fills against expected prices.
        
        This is the main validation method that:
        1. Calculates deviation from expected prices
        2. Determines if soft stop is triggered (> 0.5% deviation)
        3. Re-evaluates profitability at actual fill prices
        4. Returns action recommendation
        
        Args:
            asgard_fill: Fill information for Asgard leg
            hyperliquid_fill: Fill information for Hyperliquid leg
            expected_spread: Expected price spread between venues
            opportunity: Original opportunity for re-evaluation
            
        Returns:
            ValidationResult with validation status and action recommendation
        """
        # Step 1: Calculate deviations
        asgard_dev = self._calculate_deviation(
            asgard_fill.filled_price,
            asgard_fill.expected_price,
        )
        hyperliquid_dev = self._calculate_deviation(
            hyperliquid_fill.filled_price,
            hyperliquid_fill.expected_price,
        )
        max_dev = max(asgard_dev, hyperliquid_dev)
        
        # Step 2: Check if deviation triggers soft stop
        soft_stop_triggered = max_dev > self.max_deviation
        
        # Step 3: Re-evaluate profitability if soft stop triggered
        should_unwind = False
        apy_at_fills = opportunity.total_expected_apy
        
        if soft_stop_triggered:
            apy_at_fills = await self._recalculate_apy_at_fills(
                asgard_fill,
                hyperliquid_fill,
                opportunity,
            )
            # Only unwind if APY < 0 (unprofitable)
            should_unwind = apy_at_fills < 0
        
        # Step 4: Determine action
        if not soft_stop_triggered:
            action = "proceed"
            is_valid = True
        elif should_unwind:
            action = "hard_stop"
            is_valid = False
        else:
            action = "soft_stop"
            is_valid = True  # Still valid, just flagged
        
        # Build result
        result = ValidationResult(
            is_valid=is_valid,
            action=action,
            asgard_fill=asgard_fill,
            hyperliquid_fill=hyperliquid_fill,
            asgard_deviation=asgard_dev,
            hyperliquid_deviation=hyperliquid_dev,
            max_deviation=max_dev,
            opportunity_at_entry=opportunity,
            apy_at_fills=apy_at_fills,
            soft_stop_triggered=soft_stop_triggered,
            soft_stop_reason=self._get_soft_stop_reason(
                asgard_dev, hyperliquid_dev, max_dev
            ) if soft_stop_triggered else None,
            should_unwind=should_unwind,
        )
        
        # Log result
        self._log_validation_result(result)
        
        return result
    
    def validate_quick(
        self,
        asgard_fill_price: Decimal,
        hyperliquid_fill_price: Decimal,
        asgard_expected: Decimal,
        hyperliquid_expected: Decimal,
    ) -> ValidationResult:
        """
        Quick validation without full opportunity re-evaluation.
        
        Use this for fast checks when full profitability recalculation
        is not needed.
        
        Args:
            asgard_fill_price: Actual Asgard fill price
            hyperliquid_fill_price: Actual Hyperliquid fill price
            asgard_expected: Expected Asgard price
            hyperliquid_expected: Expected Hyperliquid price
            
        Returns:
            ValidationResult with deviation analysis
        """
        asgard_dev = self._calculate_deviation(asgard_fill_price, asgard_expected)
        hyperliquid_dev = self._calculate_deviation(hyperliquid_fill_price, hyperliquid_expected)
        max_dev = max(asgard_dev, hyperliquid_dev)
        
        soft_stop = max_dev > self.max_deviation
        
        if soft_stop:
            action = "soft_stop"
            is_valid = True  # Need further analysis
        else:
            action = "proceed"
            is_valid = True
        
        return ValidationResult(
            is_valid=is_valid,
            action=action,
            asgard_deviation=asgard_dev,
            hyperliquid_deviation=hyperliquid_dev,
            max_deviation=max_dev,
            soft_stop_triggered=soft_stop,
            soft_stop_reason="Fill deviation > threshold" if soft_stop else None,
            notes=[f"Quick validation: max_dev={max_dev:.4%}"],
        )
    
    async def _recalculate_apy_at_fills(
        self,
        asgard_fill: FillInfo,
        hyperliquid_fill: FillInfo,
        original_opportunity: ArbitrageOpportunity,
    ) -> Decimal:
        """
        Re-calculate APY using actual fill prices.
        
        Soft Stop Logic:
        - Re-evaluate total APY at actual filled prices
        - Account for any slippage/costs from deviation
        - Return new APY to determine if position should be unwound
        
        Args:
            asgard_fill: Asgard fill information
            hyperliquid_fill: Hyperliquid fill information
            original_opportunity: Original opportunity with expected prices
            
        Returns:
            Re-calculated APY at fill prices
        """
        # Get original APY components
        original_apy = original_opportunity.total_expected_apy
        
        # Calculate price impact from fills
        asgard_impact = self._calculate_price_impact(
            asgard_fill.filled_price,
            asgard_fill.expected_price,
            is_long=True,
        )
        hyperliquid_impact = self._calculate_price_impact(
            hyperliquid_fill.filled_price,
            hyperliquid_fill.expected_price,
            is_long=False,
        )
        
        # Total impact on APY
        # Assuming price impact translates directly to yield reduction
        total_impact = asgard_impact + hyperliquid_impact
        
        # Adjust APY
        adjusted_apy = original_apy - total_impact
        
        logger.debug(
            f"APY recalculation: original={original_apy:.4%}, "
            f"adjusted={adjusted_apy:.4%}, impact={total_impact:.4%}"
        )
        
        return adjusted_apy
    
    def _calculate_deviation(
        self,
        actual: Decimal,
        expected: Decimal,
    ) -> Decimal:
        """
        Calculate percentage deviation.
        
        Args:
            actual: Actual filled price
            expected: Expected price
            
        Returns:
            Deviation as percentage (e.g., 0.005 = 0.5%)
        """
        if expected == 0:
            return Decimal("0")
        
        return abs(actual - expected) / expected
    
    def _calculate_price_impact(
        self,
        filled_price: Decimal,
        expected_price: Decimal,
        is_long: bool,
    ) -> Decimal:
        """
        Calculate price impact on APY.
        
        For longs: Higher fill price = worse entry = lower APY
        For shorts: Lower fill price = worse entry = lower APY
        
        Args:
            filled_price: Actual fill price
            expected_price: Expected price
            is_long: True if long position
            
        Returns:
            Impact as percentage of APY
        """
        if expected_price == 0:
            return Decimal("0")
        
        price_diff = filled_price - expected_price
        
        if is_long:
            # For long: positive diff (filled higher) is bad
            # Impact is negative on APY
            if price_diff > 0:
                return price_diff / expected_price
            else:
                # Filled better than expected
                return Decimal("0")  # Don't improve APY beyond expected
        else:
            # For short: negative diff (filled lower) is bad
            # Impact is negative on APY
            if price_diff < 0:
                return abs(price_diff) / expected_price
            else:
                # Filled better than expected
                return Decimal("0")
    
    def _get_soft_stop_reason(
        self,
        asgard_dev: Decimal,
        hyperliquid_dev: Decimal,
        max_dev: Decimal,
    ) -> str:
        """Generate reason string for soft stop."""
        if asgard_dev > self.max_deviation and hyperliquid_dev > self.max_deviation:
            return f"Both fills exceeded deviation threshold ({max_dev:.4%})"
        elif asgard_dev > self.max_deviation:
            return f"Asgard fill exceeded deviation threshold ({asgard_dev:.4%})"
        else:
            return f"Hyperliquid fill exceeded deviation threshold ({hyperliquid_dev:.4%})"
    
    def _log_validation_result(self, result: ValidationResult) -> None:
        """Log validation result appropriately."""
        if result.action == "proceed":
            logger.info(
                f"Fill validation passed: max_dev={result.max_deviation:.4%} "
                f"({result.max_deviation * self.BPS:.1f} bps)"
            )
        elif result.action == "soft_stop":
            logger.warning(
                f"SOFT STOP triggered: {result.soft_stop_reason}. "
                f"Position still profitable (APY={result.apy_at_fills:.4%}), "
                f"holding position."
            )
        else:  # hard_stop
            logger.error(
                f"HARD STOP triggered: {result.soft_stop_reason}. "
                f"Position unprofitable (APY={result.apy_at_fills:.4%}), "
                f"unwinding position."
            )
    
    def create_position_reference(
        self,
        consensus_result: ConsensusResult,
    ) -> PositionReference:
        """
        Create a PositionReference from consensus result.
        
        Args:
            consensus_result: Price consensus result
            
        Returns:
            PositionReference for tracking entry prices
        """
        from datetime import datetime
        
        return PositionReference(
            asgard_entry_price=consensus_result.asgard_price,
            hyperliquid_entry_price=consensus_result.hyperliquid_price,
            max_acceptable_deviation=self.max_deviation,
            timestamp=datetime.utcnow().isoformat(),
        )
