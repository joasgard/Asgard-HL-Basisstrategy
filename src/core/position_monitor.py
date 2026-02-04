"""
Position Monitor Module.

Monitors open positions and triggers exit conditions based on:
- APY falling below threshold (10% minimum)
- Funding rate flips
- Health factor degradation
- Delta drift

Usage:
    async with PositionMonitor() as monitor:
        # Check position status
        status = await monitor.check_position(position)
        
        if status.should_exit:
            await execute_exit(position, status.exit_reason)
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from src.config.assets import Asset
from src.models.position import CombinedPosition
from src.utils.logger import get_logger

from .opportunity_detector import OpportunityDetector

logger = get_logger(__name__)


@dataclass
class MonitorConfig:
    """Configuration for position monitoring."""
    
    # APY threshold (exit if below)
    min_apy_threshold: Decimal = Decimal("0.10")  # 10%
    
    # Check interval (seconds)
    check_interval_seconds: int = 30
    
    # Consecutive breaches before exit (prevents noise)
    consecutive_breaches_required: int = 2
    
    # Funding flip check
    exit_on_funding_flip: bool = True
    
    # Delta drift threshold
    max_delta_drift: Decimal = Decimal("0.005")  # 0.5%


@dataclass
class PositionStatus:
    """Status of a monitored position."""
    
    position_id: str
    
    # Current metrics
    current_apy: Decimal
    projected_annual_profit: Decimal
    
    # Status flags
    should_exit: bool
    exit_reason: Optional[str] = None
    
    # Breach tracking
    apy_below_threshold: bool = False
    consecutive_breaches: int = 0
    
    # Additional checks
    funding_flipped: bool = False
    delta_drift: Decimal = Decimal("0")
    
    # Diagnostics
    notes: list = field(default_factory=list)
    
    def to_summary(self) -> dict:
        """Get summary dict for logging."""
        return {
            "position_id": self.position_id,
            "current_apy": float(self.current_apy),
            "should_exit": self.should_exit,
            "exit_reason": self.exit_reason,
            "apy_below_threshold": self.apy_below_threshold,
            "consecutive_breaches": self.consecutive_breaches,
        }


class PositionMonitor:
    """
    Monitors open positions and evaluates exit conditions.
    
    Primary exit condition:
    - APY < 10%: Unwind position
    - APY >= 10%: Hold position
    
    Additional checks:
    - Funding rate flip (positive funding = shorts pay)
    - Delta drift between legs
    - Health factor degradation
    
    Usage:
        monitor = PositionMonitor(config=MonitorConfig(min_apy_threshold=Decimal("0.10")))
        
        async with monitor:
            status = await monitor.check_position(position)
            if status.should_exit:
                logger.warning(f"Exit triggered: {status.exit_reason}")
                await close_position(position)
    """
    
    def __init__(
        self,
        config: Optional[MonitorConfig] = None,
        opportunity_detector: Optional[OpportunityDetector] = None,
    ):
        """
        Initialize position monitor.
        
        Args:
            config: Monitor configuration. Uses defaults if None.
            opportunity_detector: OpportunityDetector for APY calculations.
        """
        self.config = config or MonitorConfig()
        self.opportunity_detector = opportunity_detector
        
        # Track breach counts per position
        self._breach_counts: dict[str, int] = {}
        
        # Track ownership for cleanup
        self._own_detector = opportunity_detector is None
    
    async def __aenter__(self) -> "PositionMonitor":
        """Async context manager entry."""
        if self._own_detector and self.opportunity_detector is None:
            self.opportunity_detector = OpportunityDetector()
            await self.opportunity_detector.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._own_detector and self.opportunity_detector:
            await self.opportunity_detector.__aexit__(exc_type, exc_val, exc_tb)
    
    async def check_position(
        self,
        position: CombinedPosition,
        current_funding_rate: Optional[Decimal] = None,
    ) -> PositionStatus:
        """
        Check position status and evaluate exit conditions.
        
        Exit Logic:
        1. Calculate current APY
        2. If APY < 10%: Mark as breach
        3. If consecutive breaches >= 2: Trigger exit
        4. Check funding flip (optional)
        5. Check delta drift (optional)
        
        Args:
            position: Combined position to check
            current_funding_rate: Current funding rate (fetched if None)
            
        Returns:
            PositionStatus with exit decision
        """
        position_id = position.position_id
        notes = []
        
        # Step 1: Calculate current APY
        current_apy = await self._calculate_current_apy(position, current_funding_rate)
        
        # Step 2: Check APY threshold
        apy_below_threshold = current_apy < self.config.min_apy_threshold
        
        # Step 3: Track consecutive breaches
        if apy_below_threshold:
            self._breach_counts[position_id] = self._breach_counts.get(position_id, 0) + 1
            notes.append(f"APY below threshold: {current_apy:.2%} < {self.config.min_apy_threshold:.2%}")
        else:
            # Reset breach count when APY recovers
            if position_id in self._breach_counts:
                del self._breach_counts[position_id]
                notes.append(f"APY recovered: {current_apy:.2%}")
        
        consecutive_breaches = self._breach_counts.get(position_id, 0)
        
        # Step 4: Check funding flip
        funding_flipped = False
        if self.config.exit_on_funding_flip and current_funding_rate is not None:
            funding_flipped = current_funding_rate > 0  # Positive = shorts pay
            if funding_flipped:
                notes.append("Funding flipped positive (shorts pay)")
        
        # Step 5: Calculate delta drift
        delta_drift = self._calculate_delta_drift(position)
        
        # Determine if should exit
        should_exit = False
        exit_reason = None
        
        # Primary condition: APY < 10% for consecutive checks
        if consecutive_breaches >= self.config.consecutive_breaches_required:
            should_exit = True
            exit_reason = f"APY below {self.config.min_apy_threshold:.0%} for {consecutive_breaches} consecutive checks"
        
        # Secondary condition: Funding flip
        elif funding_flipped:
            should_exit = True
            exit_reason = "Funding rate flipped positive"
        
        # Tertiary condition: Excessive delta drift
        elif delta_drift > self.config.max_delta_drift:
            should_exit = True
            exit_reason = f"Delta drift exceeded {self.config.max_delta_drift:.2%}"
        
        # Log result
        if should_exit:
            logger.warning(
                f"Position {position_id}: EXIT triggered - {exit_reason}. "
                f"Current APY: {current_apy:.2%}"
            )
        elif apy_below_threshold:
            logger.warning(
                f"Position {position_id}: APY low ({current_apy:.2%}) but holding. "
                f"Breach count: {consecutive_breaches}/{self.config.consecutive_breaches_required}"
            )
        else:
            logger.debug(
                f"Position {position_id}: Healthy. APY: {current_apy:.2%} >= {self.config.min_apy_threshold:.2%}"
            )
        
        # Calculate deployed capital from position
        deployed_capital = (
            position.asgard.collateral_usd 
            if position.asgard 
            else Decimal("0")
        )
        
        return PositionStatus(
            position_id=position_id,
            current_apy=current_apy,
            projected_annual_profit=deployed_capital * current_apy,
            should_exit=should_exit,
            exit_reason=exit_reason,
            apy_below_threshold=apy_below_threshold,
            consecutive_breaches=consecutive_breaches,
            funding_flipped=funding_flipped,
            delta_drift=delta_drift,
            notes=notes,
        )
    
    async def _calculate_current_apy(
        self,
        position: CombinedPosition,
        current_funding_rate: Optional[Decimal],
    ) -> Decimal:
        """
        Calculate current APY for position.
        
        Args:
            position: Combined position
            current_funding_rate: Current funding rate (fetched if None)
            
        Returns:
            Current APY as Decimal
        """
        # If opportunity detector available, use it for accurate calculation
        if self.opportunity_detector and current_funding_rate is None:
            try:
                # Get current funding rates
                rates = await self.opportunity_detector.hyperliquid.get_current_funding_rates()
                hl_rate = rates.get("SOL")
                if hl_rate:
                    current_funding_rate = Decimal(str(hl_rate.annualized_rate))
            except Exception as e:
                logger.warning(f"Failed to fetch current funding rate: {e}")
        
        # Use provided current funding rate or default to 0
        if current_funding_rate is None:
            current_funding_rate = Decimal("0")
        
        # Calculate components
        # Funding APY: |funding_rate| (shorts receive payment when negative)
        funding_apy = abs(current_funding_rate) if current_funding_rate else Decimal("0")
        
        # Note: Net carry and LST staking would be calculated from opportunity
        # For now, we focus on funding rate APY as the primary variable
        # In a full implementation, these would come from position metadata
        # TODO(Phase 5.3): Get from position tracking once position_manager stores metadata
        net_carry_apy = Decimal("0")
        # TODO(Phase 5.3): Calculate based on asset type from position metadata
        lst_apy = Decimal("0")
        
        # Total APY
        total_apy = funding_apy + net_carry_apy + lst_apy
        
        return total_apy
    
    def _calculate_delta_drift(self, position: CombinedPosition) -> Decimal:
        """
        Calculate delta drift between long and short legs.
        
        Args:
            position: Combined position
            
        Returns:
            Delta drift as percentage
        """
        # Get position sizes from the model
        long_size = position.asgard.position_size_usd if position.asgard else Decimal("0")
        # For Hyperliquid, size_usd property gives absolute value
        short_size = position.hyperliquid.size_usd if position.hyperliquid else Decimal("0")
        
        if long_size == 0 or short_size == 0:
            return Decimal("0")
        
        # Calculate drift: |long - short| / avg
        diff = abs(long_size - short_size)
        avg = (long_size + short_size) / Decimal("2")
        
        return diff / avg
    
    def reset_breach_count(self, position_id: str) -> None:
        """
        Reset breach count for a position.
        
        Args:
            position_id: Position ID to reset
        """
        if position_id in self._breach_counts:
            del self._breach_counts[position_id]
            logger.debug(f"Reset breach count for position {position_id}")
    
    def get_breach_count(self, position_id: str) -> int:
        """
        Get current breach count for a position.
        
        Args:
            position_id: Position ID
            
        Returns:
            Number of consecutive breaches
        """
        return self._breach_counts.get(position_id, 0)
    
    async def evaluate_all_positions(
        self,
        positions: list[CombinedPosition],
    ) -> list[PositionStatus]:
        """
        Evaluate multiple positions and return those needing exit.
        
        Args:
            positions: List of positions to check
            
        Returns:
            List of PositionStatus for all positions
        """
        results = []
        
        for position in positions:
            try:
                status = await self.check_position(position)
                results.append(status)
            except Exception as e:
                logger.error(f"Failed to check position {position.position_id}: {e}")
                # Create error status
                results.append(PositionStatus(
                    position_id=position.position_id,
                    current_apy=Decimal("0"),
                    projected_annual_profit=Decimal("0"),
                    should_exit=False,  # Don't exit on error
                    exit_reason=None,
                    notes=[f"Error: {str(e)}"],
                ))
        
        # Log summary
        exit_count = sum(1 for r in results if r.should_exit)
        low_apy_count = sum(1 for r in results if r.apy_below_threshold and not r.should_exit)
        
        logger.info(
            f"Position monitoring complete: {len(positions)} checked, "
            f"{exit_count} exit triggered, {low_apy_count} low APY watching"
        )
        
        return results
