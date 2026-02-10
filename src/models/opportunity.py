"""
Opportunity detection models.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.models.common import Asset, Protocol
from src.models.funding import FundingRate, AsgardRates


class OpportunityScore(BaseModel):
    """Scoring breakdown for an arbitrage opportunity."""
    
    # Components (all as APY on deployed capital)
    funding_apy: Decimal = Field(description="Annual yield from funding payments")
    net_carry_apy: Decimal = Field(description="Net carry from lending - borrowing")
    lst_staking_apy: Decimal = Field(default=Decimal("0"), description="LST staking yield")
    
    # Costs
    estimated_gas_cost_apy: Decimal = Field(default=Decimal("0"), description="Gas costs annualized")
    estimated_slippage_apy: Decimal = Field(default=Decimal("0"), description="Slippage costs")
    
    @property
    def total_gross_apy(self) -> Decimal:
        """Total gross yield before costs."""
        return self.funding_apy + self.net_carry_apy + self.lst_staking_apy
    
    @property
    def total_net_apy(self) -> Decimal:
        """Total net yield after costs."""
        return self.total_gross_apy - self.estimated_gas_cost_apy - self.estimated_slippage_apy
    
    @property
    def is_profitable(self) -> bool:
        """True if total net APY > 0."""
        return self.total_net_apy > 0


class ArbitrageOpportunity(BaseModel):
    """
    A detected funding rate arbitrage opportunity.
    
    Represents the complete opportunity including both legs:
    - Long: Asgard spot/margin position
    - Short: Hyperliquid perpetual position
    """
    
    # Identification
    id: str = Field(description="Unique opportunity ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Asset configuration
    asset: Asset = Field(description="Long asset (SOL, jitoSOL, etc.)")
    
    # Asgard leg
    selected_protocol: Protocol = Field(description="Best protocol for long position")
    asgard_rates: AsgardRates = Field(description="Rates from selected protocol")
    
    # Hyperliquid leg
    hyperliquid_coin: str = Field(default="SOL", description="Perp coin (always SOL)")
    current_funding: FundingRate = Field(description="Current funding rate")
    predicted_funding: Optional[FundingRate] = Field(None, description="Predicted next funding")
    
    # Funding volatility check
    funding_volatility: Decimal = Field(description="1-week funding volatility (std dev)")
    
    # Sizing
    leverage: Decimal = Field(default=Decimal("3"), description="Position leverage")
    deployed_capital_usd: Decimal = Field(description="Capital to deploy")
    position_size_usd: Decimal = Field(description="Total position size (deployed × leverage)")
    
    # Scoring
    score: OpportunityScore = Field(description="Calculated opportunity score")
    
    # Validation results
    price_deviation: Decimal = Field(description="Price deviation between venues")
    preflight_checks_passed: bool = Field(default=False)
    
    # Metadata
    expires_at: Optional[datetime] = Field(None, description="Opportunity expiration")
    
    @field_validator("leverage")
    @classmethod
    def validate_leverage(cls, v: Decimal) -> Decimal:
        if not Decimal("1.1") <= v <= Decimal("4"):
            raise ValueError("leverage must be between 1.1 and 4")
        return v
    
    @property
    def total_expected_apy(self) -> Decimal:
        """Total expected APY from this opportunity."""
        return self.score.total_net_apy
    
    @property
    def expected_annual_profit(self) -> Decimal:
        """Expected annual profit in USD."""
        return self.deployed_capital_usd * self.total_expected_apy
    
    @property
    def meets_entry_criteria(self) -> bool:
        """
        Check if opportunity meets all entry criteria.
        
        Entry criteria:
        1. Current funding < 0 (shorts paid)
        2. Predicted funding < 0 (shorts will be paid) - conservative mode
        3. Total APY > 0
        4. Funding volatility < 50%
        5. Price deviation < 0.5%
        6. Preflight checks passed
        """
        # Check funding signs
        if not self.current_funding.is_negative:
            return False
        
        # Conservative: both current and predicted must be negative
        if self.predicted_funding and not self.predicted_funding.is_negative:
            return False
        
        # Check profitability
        if not self.score.is_profitable:
            return False
        
        # Check volatility (< 50%)
        if self.funding_volatility > Decimal("0.5"):
            return False
        
        # Check price deviation (< 0.5%)
        if self.price_deviation > Decimal("0.005"):
            return False
        
        # Check preflight
        if not self.preflight_checks_passed:
            return False
        
        return True
    
    def to_summary(self) -> dict:
        """Get a summary dict for logging."""
        return {
            "opportunity_id": self.id,
            "asset": self.asset.value,
            "protocol": self.selected_protocol.name,
            "leverage": float(self.leverage),
            "deployed_usd": float(self.deployed_capital_usd),
            "position_size_usd": float(self.position_size_usd),
            "funding_apy": float(self.score.funding_apy),
            "net_carry_apy": float(self.score.net_carry_apy),
            "lst_apy": float(self.score.lst_staking_apy),
            "total_net_apy": float(self.total_expected_apy),
            "expected_annual_profit": float(self.expected_annual_profit),
            "meets_criteria": self.meets_entry_criteria,
        }


class OpportunityFilter(BaseModel):
    """Configuration for filtering opportunities."""
    
    min_total_apy: Decimal = Field(default=Decimal("0.01"), description="Minimum 1% APY")
    max_funding_volatility: Decimal = Field(default=Decimal("0.5"), description="Max 50% volatility")
    max_price_deviation: Decimal = Field(default=Decimal("0.005"), description="Max 0.5% deviation")
    require_predicted_negative: bool = Field(default=True, description="Conservative mode")
    
    def filter(self, opportunity: ArbitrageOpportunity) -> bool:
        """Apply filter to an opportunity."""
        if opportunity.total_expected_apy < self.min_total_apy:
            return False
        
        if opportunity.funding_volatility > self.max_funding_volatility:
            return False
        
        if opportunity.price_deviation > self.max_price_deviation:
            return False
        
        if self.require_predicted_negative:
            if opportunity.predicted_funding and not opportunity.predicted_funding.is_negative:
                return False
        
        return True
