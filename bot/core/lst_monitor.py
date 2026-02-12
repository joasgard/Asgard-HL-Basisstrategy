"""
LST Correlation Monitor for Asgard Basis.

Monitors LST (Liquid Staking Token) peg status to detect depegs
that could impact delta neutrality. LSTs can trade at premium or
discount to underlying SOL based on staking rewards and market conditions.

Key LSTs monitored:
- jitoSOL: Jito liquid staking
- jupSOL: Jupiter liquid staking  
- INF: Infinity LST basket

Peg thresholds (from spec 8.1):
- Premium > 3% or Discount > 1%: Warning
- Premium > 5% or Discount > 2%: Emergency close
"""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, List, Callable
from datetime import datetime

from shared.config.assets import Asset, get_asset_metadata
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class PegStatus(Enum):
    """LST peg status."""
    NORMAL = "normal"           # Within normal range
    WARNING = "warning"         # Approaching threshold
    CRITICAL = "critical"       # Exceeds critical threshold


@dataclass
class PegCheckResult:
    """Result of LST peg check."""
    
    lst_asset: Asset
    lst_price_usd: Decimal
    sol_price_usd: Decimal
    premium_pct: Decimal  # Positive = premium, negative = discount
    
    status: PegStatus
    
    # Thresholds that were crossed
    warning_threshold_crossed: Optional[str] = None  # "premium" or "discount"
    critical_threshold_crossed: Optional[str] = None  # "premium" or "discount"
    
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    @property
    def is_depegged(self) -> bool:
        """True if LST is depegged (premium/discount beyond warning)."""
        return self.status != PegStatus.NORMAL
    
    @property
    def is_critical(self) -> bool:
        """True if critical threshold crossed."""
        return self.status == PegStatus.CRITICAL
    
    @property
    def is_premium(self) -> bool:
        """True if LST trading at premium to SOL."""
        return self.premium_pct > 0
    
    @property
    def is_discount(self) -> bool:
        """True if LST trading at discount to SOL."""
        return self.premium_pct < 0


@dataclass
class LSTDeltaAdjustment:
    """Delta adjustment for LST position based on peg status."""
    
    original_delta_usd: Decimal
    adjusted_delta_usd: Decimal
    adjustment_usd: Decimal
    
    # Explanation of adjustment
    reason: str


class LSTMonitor:
    """
    Monitors LST peg status and calculates effective delta.
    
    LSTs accumulate staking rewards, causing their value to drift
    relative to SOL over time. This monitor:
    1. Tracks LST/SOL price ratio
    2. Detects depegs (premium/discount)
    3. Calculates effective delta accounting for peg deviation
    4. Triggers alerts on threshold breaches
    
    Thresholds (from spec 8.1):
    - Warning Premium: 3%
    - Critical Premium: 5%
    - Warning Discount: 1%
    - Critical Discount: 2%
    
    Usage:
        monitor = LSTMonitor()
        
        # Check single LST
        result = await monitor.check_lst_peg(Asset.JITOSOL)
        if result.is_critical:
            await monitor.emergency_close(lst_mint)
        
        # Get effective delta for position
        adjusted_delta = monitor.calculate_effective_delta(position)
    
    Args:
        warning_premium: Premium threshold for warning (default: 3%)
        critical_premium: Premium threshold for critical (default: 5%)
        warning_discount: Discount threshold for warning (default: 1%)
        critical_discount: Discount threshold for critical (default: 2%)
    """
    
    # Default thresholds from spec section 8.1
    WARNING_PREMIUM = Decimal("0.03")    # 3%
    CRITICAL_PREMIUM = Decimal("0.05")   # 5%
    WARNING_DISCOUNT = Decimal("0.01")   # 1%
    CRITICAL_DISCOUNT = Decimal("0.02")  # 2%
    
    # LST assets to monitor
    LST_ASSETS = [Asset.JITOSOL, Asset.JUPSOL, Asset.INF]
    
    def __init__(
        self,
        warning_premium: Optional[Decimal] = None,
        critical_premium: Optional[Decimal] = None,
        warning_discount: Optional[Decimal] = None,
        critical_discount: Optional[Decimal] = None,
    ):
        self.warning_premium = warning_premium or self.WARNING_PREMIUM
        self.critical_premium = critical_premium or self.CRITICAL_PREMIUM
        self.warning_discount = warning_discount or self.WARNING_DISCOUNT
        self.critical_discount = critical_discount or self.CRITICAL_DISCOUNT
        
        # Alert callbacks
        self._warning_callbacks: List[Callable[[PegCheckResult], None]] = []
        self._critical_callbacks: List[Callable[[PegCheckResult], None]] = []
        
        logger.info(
            f"LSTMonitor initialized: "
            f"premium={float(self.warning_premium)*100}%/{float(self.critical_premium)*100}%, "
            f"discount={float(self.warning_discount)*100}%/{float(self.critical_discount)*100}%"
        )
    
    def add_warning_callback(self, callback: Callable[[PegCheckResult], None]):
        """Add callback for warning alerts."""
        self._warning_callbacks.append(callback)
    
    def add_critical_callback(self, callback: Callable[[PegCheckResult], None]):
        """Add callback for critical alerts."""
        self._critical_callbacks.append(callback)
    
    def check_lst_peg(
        self,
        lst_asset: Asset,
        lst_price_usd: Decimal,
        sol_price_usd: Decimal,
    ) -> PegCheckResult:
        """
        Check LST peg status against SOL.
        
        Args:
            lst_asset: The LST asset (jitoSOL, jupSOL, INF)
            lst_price_usd: Current LST price in USD
            sol_price_usd: Current SOL price in USD
            
        Returns:
            PegCheckResult with status and threshold info
        """
        if lst_asset not in self.LST_ASSETS:
            raise ValueError(f"Asset {lst_asset} is not an LST")
        
        # Calculate premium/discount
        # Premium = (LST_price / SOL_price) - 1
        premium_pct = (lst_price_usd / sol_price_usd) - Decimal("1")
        
        # Determine status
        status = PegStatus.NORMAL
        warning_crossed = None
        critical_crossed = None
        
        # Check premium thresholds
        if premium_pct >= self.critical_premium:
            status = PegStatus.CRITICAL
            critical_crossed = "premium"
        elif premium_pct >= self.warning_premium:
            status = PegStatus.WARNING
            warning_crossed = "premium"
        # Check discount thresholds (premium is negative)
        elif premium_pct <= -self.critical_discount:
            status = PegStatus.CRITICAL
            critical_crossed = "discount"
        elif premium_pct <= -self.warning_discount:
            status = PegStatus.WARNING
            warning_crossed = "discount"
        
        result = PegCheckResult(
            lst_asset=lst_asset,
            lst_price_usd=lst_price_usd,
            sol_price_usd=sol_price_usd,
            premium_pct=premium_pct,
            status=status,
            warning_threshold_crossed=warning_crossed,
            critical_threshold_crossed=critical_crossed,
        )
        
        # Log and trigger callbacks
        if status == PegStatus.CRITICAL:
            logger.error(
                f"CRITICAL LST depeg: {lst_asset.value} at "
                f"{float(premium_pct)*100:+.2f}% "
                f"({critical_crossed})"
            )
            for callback in self._critical_callbacks:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"Critical callback error: {e}")
        elif status == PegStatus.WARNING:
            logger.warning(
                f"LST warning: {lst_asset.value} at "
                f"{float(premium_pct)*100:+.2f}% "
                f"({warning_crossed})"
            )
            for callback in self._warning_callbacks:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"Warning callback error: {e}")
        
        return result
    
    def check_all_lst_pegs(
        self,
        prices: Dict[Asset, Decimal],
    ) -> Dict[Asset, PegCheckResult]:
        """
        Check peg status for all LSTs.
        
        Args:
            prices: Dict mapping assets to their USD prices
            
        Returns:
            Dict mapping LST assets to their peg check results
        """
        sol_price = prices.get(Asset.SOL)
        if sol_price is None:
            raise ValueError("SOL price required for peg checks")
        
        results = {}
        for lst_asset in self.LST_ASSETS:
            lst_price = prices.get(lst_asset)
            if lst_price is not None:
                results[lst_asset] = self.check_lst_peg(
                    lst_asset, lst_price, sol_price
                )
        
        return results
    
    def calculate_effective_delta(
        self,
        lst_asset: Asset,
        position_delta_usd: Decimal,
        lst_price_usd: Decimal,
        sol_price_usd: Decimal,
    ) -> LSTDeltaAdjustment:
        """
        Calculate effective delta accounting for LST peg deviation.
        
        When LST trades at premium/discount, the effective delta
        differs from the nominal position delta.
        
        Example:
        - Position: $10k jitoSOL long
        - jitoSOL at 4% premium to SOL
        - Effective SOL exposure: $10k / 1.04 = $9,615
        - Delta adjustment: -$385 (reduced long exposure)
        
        Args:
            lst_asset: The LST asset
            position_delta_usd: Current position delta in USD
            lst_price_usd: LST price in USD
            sol_price_usd: SOL price in USD
            
        Returns:
            LSTDeltaAdjustment with adjusted delta
        """
        if lst_asset not in self.LST_ASSETS:
            # Not an LST, no adjustment needed
            return LSTDeltaAdjustment(
                original_delta_usd=position_delta_usd,
                adjusted_delta_usd=position_delta_usd,
                adjustment_usd=Decimal("0"),
                reason=f"{lst_asset.value} is not an LST, no adjustment needed"
            )
        
        # Calculate LST/SOL ratio
        lst_sol_ratio = lst_price_usd / sol_price_usd
        
        # Adjust delta: position in LST terms converted to SOL terms
        # If LST is at premium, each LST is worth more SOL, so delta is lower
        adjusted_delta = position_delta_usd / lst_sol_ratio
        
        adjustment = adjusted_delta - position_delta_usd
        
        # Build reason string
        premium_pct = (lst_sol_ratio - 1) * 100
        if premium_pct > 0:
            reason = f"LST premium {float(premium_pct):.2f}%: delta adjusted from " \
                    f"${float(position_delta_usd):,.2f} to ${float(adjusted_delta):,.2f}"
        elif premium_pct < 0:
            reason = f"LST discount {float(premium_pct):.2f}%: delta adjusted from " \
                    f"${float(position_delta_usd):,.2f} to ${float(adjusted_delta):,.2f}"
        else:
            reason = "LST at peg: no delta adjustment needed"
        
        logger.debug(reason)
        
        return LSTDeltaAdjustment(
            original_delta_usd=position_delta_usd,
            adjusted_delta_usd=adjusted_delta,
            adjustment_usd=adjustment,
            reason=reason,
        )
    
    def should_emergency_close(self, result: PegCheckResult) -> bool:
        """
        Determine if position should be emergency closed.
        
        Emergency close triggers:
        - Premium > 5%
        - Discount > 2%
        
        Args:
            result: Peg check result
            
        Returns:
            True if emergency close should trigger
        """
        return result.is_critical
    
    def get_threshold_summary(self) -> Dict[str, Decimal]:
        """Get current threshold configuration."""
        return {
            "warning_premium": self.warning_premium,
            "critical_premium": self.critical_premium,
            "warning_discount": self.warning_discount,
            "critical_discount": self.critical_discount,
        }
    
    def is_lst_asset(self, asset: Asset) -> bool:
        """Check if asset is an LST."""
        return asset in self.LST_ASSETS
