"""
Risk Engine for Asgard Basis.

Evaluates positions against risk thresholds and determines if/when
to exit positions based on various risk conditions.

Exit Triggers (from spec 5.2, 8.1, 8.3):
- Total APY turns negative AND closing_cost < 5min expected loss
- Asgard health_factor approaching threshold (20% away for 20s+)
- Hyperliquid margin fraction approaching threshold (20% away for 20s+)
- Price deviation > 2% between venues
- LST premium > 5% or discount > 2%
- Manual override
- Chain outage detected
"""
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

from shared.config.assets import Asset
from shared.config.settings import get_risk_limits
from shared.models.common import ExitReason
from shared.models.position import AsgardPosition, HyperliquidPosition, CombinedPosition
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class RiskLevel(Enum):
    """Risk level classification."""
    NORMAL = "normal"
    WARNING = "warning"      # Approaching threshold
    CRITICAL = "critical"    # Immediate action required


    # ExitReason is imported from shared.models.common


@dataclass
class HealthCheckResult:
    """Result of health factor check."""
    
    level: RiskLevel
    health_factor: Decimal
    threshold: Decimal
    distance_to_liquidation: Decimal  # As percentage
    
    # Proximity tracking
    in_proximity: bool  # Within 20% of threshold for 20s+
    proximity_start_time: Optional[datetime] = None
    
    @property
    def is_safe(self) -> bool:
        """True if health factor is safe."""
        return self.level == RiskLevel.NORMAL
    
    @property
    def should_close(self) -> bool:
        """True if position should be closed."""
        return self.level == RiskLevel.CRITICAL or self.in_proximity


@dataclass
class MarginCheckResult:
    """Result of margin fraction check."""
    
    level: RiskLevel
    margin_fraction: Decimal
    threshold: Decimal
    distance_to_threshold: Decimal  # As percentage
    
    # Proximity tracking
    in_proximity: bool  # Within 20% of threshold for 20s+
    proximity_start_time: Optional[datetime] = None
    
    @property
    def is_safe(self) -> bool:
        """True if margin is safe."""
        return self.level == RiskLevel.NORMAL
    
    @property
    def should_close(self) -> bool:
        """True if position should be closed."""
        return self.level == RiskLevel.CRITICAL or self.in_proximity


@dataclass
class FundingFlipCheck:
    """Result of funding flip check."""
    
    flipped: bool
    current_funding_annual: Decimal
    predicted_funding_annual: Decimal
    
    # Flip details
    was_shorts_paid: bool  # True if shorts were being paid (negative funding)
    now_longs_paid: bool   # True if longs now being paid (positive funding)


@dataclass
class ExitDecision:
    """Decision on whether to exit position."""
    
    should_exit: bool
    reason: Optional[ExitReason] = None
    level: RiskLevel = RiskLevel.NORMAL
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Cost analysis
    estimated_close_cost: Optional[Decimal] = None
    expected_loss_if_held: Optional[Decimal] = None


@dataclass
class DeltaDriftResult:
    """Result of delta drift check."""
    
    drift_ratio: Decimal  # Delta as percentage of position
    threshold: Decimal
    level: RiskLevel
    
    # Rebalance analysis
    drift_cost: Optional[Decimal] = None  # Cost of doing nothing
    rebalance_cost: Optional[Decimal] = None  # Cost to rebalance
    should_rebalance: bool = False


class RiskEngine:
    """
    Evaluates risk conditions and makes exit decisions.
    
    This engine continuously monitors positions and market conditions,
    determining when positions should be exited based on risk thresholds.
    
    Thresholds (from spec 8.1):
    
    Asgard:
    - Min Health Factor: 20%
    - Emergency Health Factor: 10%
    - Critical Health Factor: 5%
    - Liquidation Proximity: Within 20% for 20+ seconds
    
    Hyperliquid:
    - Margin Fraction Threshold: 10%
    - Liquidation Proximity: Within 20% for 20+ seconds
    
    Other:
    - Price Deviation: > 2%
    - LST Premium: > 5%
    - LST Discount: > 2%
    - Delta Drift: > 0.5% (warning), > 2% (critical)
    
    Usage:
        engine = RiskEngine()
        
        # Check Asgard health
        health = engine.check_asgard_health(position)
        if health.should_close:
            decision = engine.evaluate_exit_trigger(position)
            if decision.should_exit:
                await close_position(position)
    """
    
    # Asgard thresholds (from risk.yaml)
    MIN_HEALTH_FACTOR = Decimal("0.20")
    EMERGENCY_HEALTH_FACTOR = Decimal("0.10")
    CRITICAL_HEALTH_FACTOR = Decimal("0.05")
    
    # Hyperliquid thresholds (from risk.yaml)
    MARGIN_FRACTION_THRESHOLD = Decimal("0.10")
    
    # Liquidation proximity (from spec 8.1)
    LIQUIDATION_PROXIMITY_PCT = Decimal("0.20")  # 20% away
    LIQUIDATION_PROXIMITY_DURATION = 20  # seconds
    
    # Other thresholds
    MAX_PRICE_DEVIATION = Decimal("0.02")  # 2%
    DELTA_DRIFT_WARNING = Decimal("0.005")  # 0.5%
    DELTA_DRIFT_CRITICAL = Decimal("0.02")  # 2%
    
    def __init__(self):
        # Load from risk config
        risk_limits = get_risk_limits()
        asgard_limits = risk_limits.get('asgard', {})
        hl_limits = risk_limits.get('hyperliquid', {})
        
        self.min_health_factor = Decimal(str(asgard_limits.get('min_health_factor', 0.20)))
        self.emergency_health_factor = Decimal(str(asgard_limits.get('emergency_health_factor', 0.10)))
        self.critical_health_factor = Decimal(str(asgard_limits.get('critical_health_factor', 0.05)))
        
        self.margin_fraction_threshold = Decimal(str(hl_limits.get('margin_fraction_threshold', 0.10)))
        
        # Proximity tracking
        self._proximity_start_times: Dict[str, datetime] = {}
        
        logger.info(
            f"RiskEngine initialized: "
            f"HF={float(self.min_health_factor):.0%}/{float(self.emergency_health_factor):.0%}/{float(self.critical_health_factor):.0%}, "
            f"MF={float(self.margin_fraction_threshold):.0%}"
        )
    
    def check_asgard_health(
        self,
        position: AsgardPosition,
        current_health_factor: Optional[Decimal] = None,
        user_id: Optional[str] = None,
    ) -> HealthCheckResult:
        """
        Check Asgard position health factor.
        
        Args:
            position: Asgard position
            current_health_factor: Current HF (uses position value if None)
            
        Returns:
            HealthCheckResult with risk level
        """
        hf = current_health_factor or position.health_factor
        
        # Calculate distance to liquidation (0% HF)
        # Distance = HF (since liquidation is at 0)
        distance_to_liquidation = hf
        
        # Determine risk level
        if hf <= self.critical_health_factor:
            level = RiskLevel.CRITICAL
        elif hf <= self.emergency_health_factor:
            level = RiskLevel.CRITICAL
        elif hf <= self.min_health_factor:
            level = RiskLevel.WARNING
        else:
            level = RiskLevel.NORMAL
        
        # Check proximity (within 20% of threshold for 20s+)
        proximity_threshold = self.min_health_factor * (Decimal("1") + self.LIQUIDATION_PROXIMITY_PCT)
        in_proximity = hf <= proximity_threshold
        
        # C4: Namespace proximity key by user_id for multi-tenant isolation
        pda_key = position.position_pda
        proximity_key = f"{user_id}:asgard_{pda_key}" if user_id else f"asgard_{pda_key}"
        proximity_start = self._update_proximity_tracking(
            proximity_key,
            in_proximity
        )
        
        proximity_triggered = (
            in_proximity and 
            proximity_start is not None and
            (datetime.utcnow() - proximity_start).total_seconds() >= self.LIQUIDATION_PROXIMITY_DURATION
        )
        
        return HealthCheckResult(
            level=level,
            health_factor=hf,
            threshold=self.min_health_factor,
            distance_to_liquidation=distance_to_liquidation,
            in_proximity=proximity_triggered,
            proximity_start_time=proximity_start,
        )
    
    def check_hyperliquid_margin(
        self,
        position: HyperliquidPosition,
        current_margin_fraction: Optional[Decimal] = None,
        user_id: Optional[str] = None,
    ) -> MarginCheckResult:
        """
        Check Hyperliquid margin fraction.
        
        Args:
            position: Hyperliquid position
            current_margin_fraction: Current MF (uses position value if None)
            
        Returns:
            MarginCheckResult with risk level
        """
        mf = current_margin_fraction or position.margin_fraction
        
        # Calculate distance to threshold
        distance_to_threshold = mf - self.margin_fraction_threshold
        
        # Determine risk level
        if mf <= self.margin_fraction_threshold * Decimal("0.5"):
            level = RiskLevel.CRITICAL
        elif mf <= self.margin_fraction_threshold:
            level = RiskLevel.WARNING
        else:
            level = RiskLevel.NORMAL
        
        # Check proximity (within 20% of threshold for 20s+)
        proximity_threshold = self.margin_fraction_threshold * (Decimal("1") + self.LIQUIDATION_PROXIMITY_PCT)
        in_proximity = mf <= proximity_threshold
        
        # C4: Namespace proximity key by user_id for multi-tenant isolation
        pos_key = position.position_id
        proximity_key = f"{user_id}:hyperliquid_{pos_key}" if user_id else f"hyperliquid_{pos_key}"
        proximity_start = self._update_proximity_tracking(
            proximity_key,
            in_proximity
        )
        
        proximity_triggered = (
            in_proximity and 
            proximity_start is not None and
            (datetime.utcnow() - proximity_start).total_seconds() >= self.LIQUIDATION_PROXIMITY_DURATION
        )
        
        return MarginCheckResult(
            level=level,
            margin_fraction=mf,
            threshold=self.margin_fraction_threshold,
            distance_to_threshold=distance_to_threshold,
            in_proximity=proximity_triggered,
            proximity_start_time=proximity_start,
        )
    
    def check_funding_flip(
        self,
        current_funding_annual: Decimal,
        predicted_funding_annual: Decimal,
        entry_funding_annual: Optional[Decimal] = None,
    ) -> FundingFlipCheck:
        """
        Check if funding has flipped (shorts no longer being paid).
        
        Args:
            current_funding_annual: Current funding rate (annualized)
            predicted_funding_annual: Predicted next funding rate
            entry_funding_annual: Funding rate at position entry
            
        Returns:
            FundingFlipCheck with flip status
        """
        # Shorts are paid when funding is negative
        shorts_currently_paid = current_funding_annual < 0
        shorts_predicted_paid = predicted_funding_annual < 0
        
        # Flip detected if shorts were paid but now longs will be paid
        flipped = shorts_currently_paid and not shorts_predicted_paid
        
        return FundingFlipCheck(
            flipped=flipped,
            current_funding_annual=current_funding_annual,
            predicted_funding_annual=predicted_funding_annual,
            was_shorts_paid=shorts_currently_paid,
            now_longs_paid=not shorts_predicted_paid,
        )
    
    def check_delta_drift(
        self,
        delta_ratio: Decimal,
        drift_cost: Optional[Decimal] = None,
        rebalance_cost: Optional[Decimal] = None,
    ) -> DeltaDriftResult:
        """
        Check if delta drift exceeds thresholds.
        
        Args:
            delta_ratio: Delta as percentage of position size
            drift_cost: Cost of continuing to hold drifted position
            rebalance_cost: Cost to rebalance position
            
        Returns:
            DeltaDriftResult with level and rebalance recommendation
        """
        abs_delta = abs(delta_ratio)
        
        if abs_delta >= self.DELTA_DRIFT_CRITICAL:
            level = RiskLevel.CRITICAL
        elif abs_delta >= self.DELTA_DRIFT_WARNING:
            level = RiskLevel.WARNING
        else:
            level = RiskLevel.NORMAL
        
        # Determine if rebalance is cost-effective
        should_rebalance = False
        if drift_cost is not None and rebalance_cost is not None:
            should_rebalance = drift_cost > rebalance_cost
        elif level == RiskLevel.CRITICAL:
            should_rebalance = True
        
        return DeltaDriftResult(
            drift_ratio=delta_ratio,
            threshold=self.DELTA_DRIFT_WARNING,
            level=level,
            drift_cost=drift_cost,
            rebalance_cost=rebalance_cost,
            should_rebalance=should_rebalance,
        )
    
    def evaluate_exit_trigger(
        self,
        position: CombinedPosition,
        current_apy: Optional[Decimal] = None,
        estimated_close_cost: Optional[Decimal] = None,
        current_health_factor: Optional[Decimal] = None,
        current_margin_fraction: Optional[Decimal] = None,
        current_funding_annual: Optional[Decimal] = None,
        predicted_funding_annual: Optional[Decimal] = None,
        price_deviation: Optional[Decimal] = None,
        lst_depegged: bool = False,
        chain_outage: Optional[str] = None,
    ) -> ExitDecision:
        """
        Evaluate all exit conditions and return exit decision.
        
        This is the main entry point for risk evaluation. It checks all
        risk conditions and returns a unified exit decision.
        
        Exit Triggers (priority order):
        1. Chain outage (immediate)
        2. Manual override (if set)
        3. Critical health/margin (immediate)
        4. LST critical depeg (immediate)
        5. Price deviation > 2%
        6. Negative APY with cost analysis
        7. Funding flip
        8. Proximity warnings (20% for 20s+)
        
        Args:
            position: Combined position to evaluate
            current_apy: Current expected APY
            estimated_close_cost: Cost to close position
            current_health_factor: Current Asgard HF
            current_margin_fraction: Current Hyperliquid MF
            current_funding_annual: Current funding rate
            predicted_funding_annual: Predicted funding rate
            price_deviation: Price deviation between venues
            lst_depegged: Whether LST is critically depegged
            chain_outage: Chain with outage (if any)
            
        Returns:
            ExitDecision with should_exit and reason
        """
        now = datetime.utcnow()
        
        # 1. Chain outage (highest priority)
        if chain_outage:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.CHAIN_OUTAGE,
                level=RiskLevel.CRITICAL,
                details={"affected_chain": chain_outage},
                timestamp=now,
            )
        
        # 2. Asgard health factor check
        asgard_health = self.check_asgard_health(
            position.asgard, current_health_factor
        )
        if asgard_health.should_close:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.HEALTH_FACTOR,
                level=asgard_health.level,
                details={
                    "health_factor": float(asgard_health.health_factor),
                    "threshold": float(asgard_health.threshold),
                    "in_proximity": asgard_health.in_proximity,
                },
                timestamp=now,
            )
        
        # 3. Hyperliquid margin check
        hyperliquid_margin = self.check_hyperliquid_margin(
            position.hyperliquid, current_margin_fraction
        )
        if hyperliquid_margin.should_close:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.MARGIN_FRACTION,
                level=hyperliquid_margin.level,
                details={
                    "margin_fraction": float(hyperliquid_margin.margin_fraction),
                    "threshold": float(hyperliquid_margin.threshold),
                    "in_proximity": hyperliquid_margin.in_proximity,
                },
                timestamp=now,
            )
        
        # 4. LST depeg (critical)
        if lst_depegged:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.LST_DEPEG,
                level=RiskLevel.CRITICAL,
                timestamp=now,
            )
        
        # 5. Price deviation
        if price_deviation and price_deviation > self.MAX_PRICE_DEVIATION:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.PRICE_DEVIATION,
                level=RiskLevel.CRITICAL,
                details={
                    "price_deviation": float(price_deviation),
                    "threshold": float(self.MAX_PRICE_DEVIATION),
                },
                timestamp=now,
            )
        
        # 6. Negative APY
        if current_apy is not None and current_apy < 0:
            # Only exit if closing cost < expected loss from holding
            # Assume 5 minutes of loss at current APY
            position_value = position.asgard.position_size_usd
            five_min_loss = position_value * abs(current_apy) * Decimal("5") / Decimal("525600")  # mins per year
            
            close_cost = estimated_close_cost or Decimal("0")
            
            if close_cost < five_min_loss:
                return ExitDecision(
                    should_exit=True,
                    reason=ExitReason.NEGATIVE_APY,
                    level=RiskLevel.WARNING,
                    details={
                        "current_apy": float(current_apy),
                        "estimated_close_cost": float(close_cost),
                        "five_min_expected_loss": float(five_min_loss),
                    },
                    estimated_close_cost=close_cost,
                    expected_loss_if_held=five_min_loss,
                    timestamp=now,
                )
        
        # 7. Funding flip
        if current_funding_annual is not None and predicted_funding_annual is not None:
            flip_check = self.check_funding_flip(
                current_funding_annual, predicted_funding_annual
            )
            if flip_check.flipped:
                return ExitDecision(
                    should_exit=True,
                    reason=ExitReason.FUNDING_FLIP,
                    level=RiskLevel.WARNING,
                    details={
                        "current_funding": float(current_funding_annual),
                        "predicted_funding": float(predicted_funding_annual),
                    },
                    timestamp=now,
                )
        
        # No exit trigger — report the worse of the two levels
        _level_order = {RiskLevel.NORMAL: 0, RiskLevel.WARNING: 1, RiskLevel.CRITICAL: 2}
        worst_level = (
            asgard_health.level
            if _level_order.get(asgard_health.level, 0) >= _level_order.get(hyperliquid_margin.level, 0)
            else hyperliquid_margin.level
        )
        return ExitDecision(
            should_exit=False,
            level=worst_level,
            timestamp=now,
        )
    
    def _update_proximity_tracking(
        self,
        key: str,
        in_proximity: bool,
    ) -> Optional[datetime]:
        """Update proximity tracking for a position."""
        if in_proximity:
            if key not in self._proximity_start_times:
                self._proximity_start_times[key] = datetime.utcnow()
            return self._proximity_start_times[key]
        else:
            if key in self._proximity_start_times:
                del self._proximity_start_times[key]
            return None
    
    def reset_proximity_tracking(self, position_id: str):
        """Reset proximity tracking for a position (e.g., after rebalance)."""
        keys_to_remove = [
            k for k in self._proximity_start_times.keys()
            if position_id in k
        ]
        for key in keys_to_remove:
            del self._proximity_start_times[key]
    
    def get_risk_summary(self, position: CombinedPosition) -> Dict[str, Any]:
        """Get comprehensive risk summary for a position."""
        asgard_health = self.check_asgard_health(position.asgard)
        hyperliquid_margin = self.check_hyperliquid_margin(position.hyperliquid)
        
        _level_order = {RiskLevel.NORMAL: 0, RiskLevel.WARNING: 1, RiskLevel.CRITICAL: 2}
        worst = (
            asgard_health.level
            if _level_order.get(asgard_health.level, 0) >= _level_order.get(hyperliquid_margin.level, 0)
            else hyperliquid_margin.level
        )
        return {
            "overall_risk": worst.value,
            "asgard": {
                "health_factor": float(asgard_health.health_factor),
                "level": asgard_health.level.value,
                "should_close": asgard_health.should_close,
            },
            "hyperliquid": {
                "margin_fraction": float(hyperliquid_margin.margin_fraction),
                "level": hyperliquid_margin.level.value,
                "should_close": hyperliquid_margin.should_close,
            },
        }
