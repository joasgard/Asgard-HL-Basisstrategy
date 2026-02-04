"""
Position Sizer for Delta Neutral Arbitrage.

Calculates optimal position sizes based on available capital,
enforcing minimum/maximum constraints and handling wallet balance mismatches.

The sizer ensures:
- Minimum position size ($1000) to make trades worthwhile
- Conservative deployment (10% default, 50% max) to preserve capital
- Equal split between Asgard (Solana) and Hyperliquid (Arbitrum)
- Proper leverage calculations (3-4x)
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, Any

from src.config.settings import get_settings, get_risk_limits
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PositionSize:
    """Calculated position size for both legs of the trade."""
    
    # Per-leg deployment (collateral for Asgard, margin for Hyperliquid)
    per_leg_deployment_usd: Decimal
    
    # Position size after leverage
    position_size_usd: Decimal
    
    # Amount borrowed (for Asgard) or notional (for Hyperliquid)
    borrowed_usd: Decimal
    
    # Actual leverage used
    leverage: Decimal
    
    # Constraints applied
    deployment_pct_used: Decimal
    was_capped_by_min: bool = False
    was_capped_by_max: bool = False
    was_capped_by_balance: bool = False


@dataclass
class SizingResult:
    """Result of position sizing calculation."""
    
    success: bool
    size: Optional[PositionSize] = None
    error: Optional[str] = None
    
    # Constraint details
    solana_balance_usd: Optional[Decimal] = None
    hyperliquid_balance_usd: Optional[Decimal] = None
    limiting_balance_usd: Optional[Decimal] = None


class PositionSizer:
    """
    Calculates position sizes for delta-neutral arbitrage.
    
    Sizing Logic:
    1. Take minimum of Solana and Hyperliquid balances (conservative)
    2. Apply deployment percentage (default 10%, max 50%)
    3. Calculate per-leg deployment (50/50 split)
    4. Calculate position size: deployment × leverage
    5. Enforce minimum position size ($1000)
    
    Example (3x leverage, $50k balances, 10% deployment):
    - Limiting balance: $50,000
    - Total deployment: $50,000 × 10% = $5,000
    - Per leg: $5,000 / 2 = $2,500
    - Position size: $2,500 × 3 = $7,500
    - Borrowed: $7,500 - $2,500 = $5,000
    
    Args:
        min_position_usd: Minimum position size (default: $1000)
        default_deployment_pct: Default deployment percentage (default: 10%)
        max_deployment_pct: Maximum deployment percentage (default: 50%)
        default_leverage: Default leverage (default: 3.0)
        max_leverage: Maximum leverage (default: 4.0)
    """
    
    # Position constraints
    MIN_POSITION_USD = Decimal("1000")
    DEFAULT_DEPLOYMENT_PCT = Decimal("0.10")  # 10% conservative
    MAX_DEPLOYMENT_PCT = Decimal("0.50")      # 50% max
    
    def __init__(
        self,
        min_position_usd: Optional[Decimal] = None,
        default_deployment_pct: Optional[Decimal] = None,
        max_deployment_pct: Optional[Decimal] = None,
        default_leverage: Optional[Decimal] = None,
        max_leverage: Optional[Decimal] = None,
    ):
        self.min_position_usd = min_position_usd or self.MIN_POSITION_USD
        self.default_deployment_pct = default_deployment_pct or self.DEFAULT_DEPLOYMENT_PCT
        self.max_deployment_pct = max_deployment_pct or self.MAX_DEPLOYMENT_PCT
        
        # Load from risk config if not provided
        risk_limits = get_risk_limits()
        self.default_leverage = default_leverage or Decimal(str(risk_limits.get('default_leverage', 3.0)))
        self.max_leverage = max_leverage or Decimal(str(risk_limits.get('max_leverage', 4.0)))
        
        logger.info(
            f"PositionSizer initialized: min=${self.min_position_usd}, "
            f"deploy={self.default_deployment_pct*100}%-{self.max_deployment_pct*100}%, "
            f"leverage={self.default_leverage}x-{self.max_leverage}x"
        )
    
    def calculate_position_size(
        self,
        solana_balance_usd: Decimal,
        hyperliquid_balance_usd: Decimal,
        deployment_pct: Optional[Decimal] = None,
        leverage: Optional[Decimal] = None,
    ) -> SizingResult:
        """
        Calculate position size based on available capital.
        
        Args:
            solana_balance_usd: Available USDC balance on Solana
            hyperliquid_balance_usd: Available USDC balance on Hyperliquid
            deployment_pct: Deployment percentage (uses default if None)
            leverage: Leverage to use (uses default if None)
            
        Returns:
            SizingResult with calculated size or error
        """
        try:
            # Validate inputs
            if solana_balance_usd < 0 or hyperliquid_balance_usd < 0:
                return SizingResult(
                    success=False,
                    error="Balances cannot be negative"
                )
            
            # Use defaults if not specified
            deployment_pct = deployment_pct or self.default_deployment_pct
            leverage = leverage or self.default_leverage
            
            # Clamp leverage to valid range
            if leverage > self.max_leverage:
                leverage = self.max_leverage
            elif leverage < Decimal("1"):
                leverage = Decimal("1")
            
            # Clamp deployment percentage
            deployment_pct = min(deployment_pct, self.max_deployment_pct)
            
            # Step 1: Find minimum balance (conservative - use limiting chain)
            limiting_balance = min(solana_balance_usd, hyperliquid_balance_usd)
            
            # Step 2: Calculate total deployment
            total_deployment = limiting_balance * deployment_pct
            
            # Step 3: Calculate per-leg deployment (50/50 split)
            per_leg_deployment = total_deployment / 2
            
            # Step 4: Calculate position size
            position_size = per_leg_deployment * leverage
            
            # Step 5: Calculate borrowed amount
            borrowed = position_size - per_leg_deployment
            
            # Check minimum position constraint
            was_capped_by_min = False
            if position_size < self.min_position_usd:
                # Scale up to minimum
                scale_factor = self.min_position_usd / position_size
                position_size = self.min_position_usd
                per_leg_deployment = position_size / leverage
                borrowed = position_size - per_leg_deployment
                total_deployment = per_leg_deployment * 2
                was_capped_by_min = True
                
                # Check if we have enough balance for minimum
                if total_deployment > limiting_balance:
                    return SizingResult(
                        success=False,
                        error=f"Insufficient balance for minimum position. "
                              f"Need ${total_deployment:.2f}, have ${limiting_balance:.2f}",
                        solana_balance_usd=solana_balance_usd,
                        hyperliquid_balance_usd=hyperliquid_balance_usd,
                        limiting_balance_usd=limiting_balance
                    )
            
            # Calculate which constraint was active
            was_capped_by_max = deployment_pct >= self.max_deployment_pct
            was_capped_by_balance = (
                limiting_balance == solana_balance_usd or 
                limiting_balance == hyperliquid_balance_usd
            )
            
            size = PositionSize(
                per_leg_deployment_usd=per_leg_deployment,
                position_size_usd=position_size,
                borrowed_usd=borrowed,
                leverage=leverage,
                deployment_pct_used=deployment_pct,
                was_capped_by_min=was_capped_by_min,
                was_capped_by_max=was_capped_by_max,
                was_capped_by_balance=was_capped_by_balance,
            )
            
            logger.info(
                f"Position size calculated: ${float(position_size):,.2f} "
                f"(@ {float(leverage)}x, per_leg=${float(per_leg_deployment):,.2f})"
            )
            
            return SizingResult(
                success=True,
                size=size,
                solana_balance_usd=solana_balance_usd,
                hyperliquid_balance_usd=hyperliquid_balance_usd,
                limiting_balance_usd=limiting_balance,
            )
            
        except Exception as e:
            logger.error(f"Position sizing failed: {e}")
            return SizingResult(
                success=False,
                error=f"Sizing calculation failed: {str(e)}"
            )
    
    def calculate_for_opportunity(
        self,
        solana_balance_usd: Decimal,
        hyperliquid_balance_usd: Decimal,
        target_size_usd: Optional[Decimal] = None,
        leverage: Optional[Decimal] = None,
    ) -> SizingResult:
        """
        Calculate position size for a specific opportunity.
        
        If target_size is provided, calculates the deployment needed to achieve it.
        Otherwise uses default deployment percentage.
        
        Args:
            solana_balance_usd: Available USDC on Solana
            hyperliquid_balance_usd: Available USDC on Hyperliquid
            target_size_usd: Desired position size (optional)
            leverage: Leverage to use (uses default if None)
            
        Returns:
            SizingResult with calculated size
        """
        leverage = leverage or self.default_leverage
        
        if target_size_usd:
            # Calculate deployment needed for target size
            # target_size = per_leg * leverage
            # per_leg = target_size / leverage
            per_leg = target_size_usd / leverage
            total_deployment = per_leg * 2
            limiting_balance = min(solana_balance_usd, hyperliquid_balance_usd)
            
            if total_deployment > limiting_balance * self.max_deployment_pct:
                # Target exceeds max deployment, fall back to max available
                logger.warning(
                    f"Target size ${float(target_size_usd):,.2f} exceeds max capacity. "
                    f"Using max available."
                )
                return self.calculate_position_size(
                    solana_balance_usd,
                    hyperliquid_balance_usd,
                    deployment_pct=self.max_deployment_pct,
                    leverage=leverage,
                )
            
            if per_leg > solana_balance_usd or per_leg > hyperliquid_balance_usd:
                # Target exceeds single leg balance
                logger.warning(
                    f"Target size ${float(target_size_usd):,.2f} exceeds single leg capacity. "
                    f"Using max available."
                )
                return self.calculate_position_size(
                    solana_balance_usd,
                    hyperliquid_balance_usd,
                    deployment_pct=self.max_deployment_pct,
                    leverage=leverage,
                )
            
            # Calculate deployment percentage needed
            deployment_pct = total_deployment / limiting_balance
            
            return self.calculate_position_size(
                solana_balance_usd,
                hyperliquid_balance_usd,
                deployment_pct=min(deployment_pct, self.max_deployment_pct),
                leverage=leverage,
            )
        
        # Use default sizing
        return self.calculate_position_size(
            solana_balance_usd,
            hyperliquid_balance_usd,
            leverage=leverage,
        )
    
    def get_max_position_size(
        self,
        solana_balance_usd: Decimal,
        hyperliquid_balance_usd: Decimal,
        leverage: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Get maximum possible position size given current balances.
        
        Args:
            solana_balance_usd: Solana balance
            hyperliquid_balance_usd: Hyperliquid balance
            leverage: Leverage (uses max if None)
            
        Returns:
            Maximum position size in USD
        """
        leverage = leverage or self.max_leverage
        limiting_balance = min(solana_balance_usd, hyperliquid_balance_usd)
        
        # Max deployment per leg
        max_per_leg = limiting_balance * self.max_deployment_pct / 2
        
        # Max position size
        return max_per_leg * leverage
    
    def can_afford_position(
        self,
        solana_balance_usd: Decimal,
        hyperliquid_balance_usd: Decimal,
        target_size_usd: Decimal,
        leverage: Optional[Decimal] = None,
    ) -> bool:
        """
        Check if current balances can support a target position size.
        
        Args:
            solana_balance_usd: Solana balance
            hyperliquid_balance_usd: Hyperliquid balance
            target_size_usd: Desired position size
            leverage: Leverage to use
            
        Returns:
            True if position is affordable
        """
        leverage = leverage or self.default_leverage
        
        # Calculate required per-leg deployment
        per_leg = target_size_usd / leverage
        total_deployment = per_leg * 2
        
        # Check if we have enough on both chains
        return (
            solana_balance_usd >= per_leg and
            hyperliquid_balance_usd >= per_leg and
            total_deployment <= min(solana_balance_usd, hyperliquid_balance_usd) * self.max_deployment_pct
        )
