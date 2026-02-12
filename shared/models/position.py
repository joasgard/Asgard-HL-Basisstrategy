"""
Position models for tracking open positions.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field

from shared.models.common import (
    Asset, Protocol, TransactionState, ExitReason, 
    PositionId, IntentId, TxSignature
)


from dataclasses import dataclass as _dataclass

@_dataclass
class PositionState:
    """Current state of a position from on-chain data."""
    
    position_pda: str
    collateral_amount: float
    borrow_amount: float
    health_factor: float


class AsgardPosition(BaseModel):
    """Asgard long position details."""
    
    # Position identification
    position_pda: str = Field(description="Position PDA on Solana")
    intent_id: IntentId = Field(description="Intent ID from creation")
    
    # Asset details
    asset: Asset = Field(description="Long asset")
    protocol: Protocol = Field(description="Protocol used")
    
    # Position sizing
    collateral_usd: Decimal = Field(description="USDC collateral amount")
    position_size_usd: Decimal = Field(description="Total position size")
    leverage: Decimal = Field(description="Position leverage")
    
    # Token amounts
    token_a_amount: Decimal = Field(description="Amount of SOL/LST tokens")
    token_b_borrowed: Decimal = Field(description="Amount of USDC borrowed")
    
    # Entry prices
    entry_price_token_a: Decimal = Field(description="Entry price of token A")
    entry_price_token_b: Decimal = Field(default=Decimal("1"), description="Entry price of USDC (always ~1)")
    
    # Current state
    current_health_factor: Decimal = Field(description="Current health factor")
    current_token_a_price: Decimal = Field(description="Current price of token A")
    
    # Timestamps
    entry_time: datetime = Field(default_factory=datetime.utcnow)
    last_update: datetime = Field(default_factory=datetime.utcnow)
    
    # Transaction tracking
    create_tx_signature: Optional[TxSignature] = None
    close_tx_signature: Optional[TxSignature] = None
    
    @property
    def is_liquidation_risk(self) -> bool:
        """Check if position is at risk of liquidation."""
        # Health factor < 0.20 is warning zone
        return self.current_health_factor < Decimal("0.20")
    
    @property
    def is_critical_liquidation_risk(self) -> bool:
        """Critical liquidation risk (< 10% away)."""
        return self.current_health_factor < Decimal("0.10")
    
    @property
    def current_value_usd(self) -> Decimal:
        """Current position value in USD."""
        return self.token_a_amount * self.current_token_a_price
    
    @property
    def pnl_usd(self) -> Decimal:
        """Unrealized PnL in USD."""
        entry_value = self.token_a_amount * self.entry_price_token_a
        current_value = self.current_value_usd
        return current_value - entry_value


class HyperliquidPosition(BaseModel):
    """Hyperliquid short perpetual position details."""
    
    # Position identification
    coin: str = Field(default="SOL", description="Perp coin")
    
    # Position sizing
    size_sol: Decimal = Field(description="Position size in SOL (negative for short)")
    entry_px: Decimal = Field(description="Entry price")
    leverage: Decimal = Field(description="Position leverage")
    
    # Margin details
    margin_used: Decimal = Field(description="Margin used for position")
    margin_fraction: Decimal = Field(description="Current margin fraction")
    account_value: Decimal = Field(description="Total account value")
    
    # Funding
    cum_funding: Decimal = Field(default=Decimal("0"), description="Cumulative funding received/paid")
    
    # Current state
    mark_px: Decimal = Field(description="Current mark price")
    liquidation_px: Optional[Decimal] = Field(None, description="Liquidation price")
    
    # Timestamps
    entry_time: datetime = Field(default_factory=datetime.utcnow)
    last_update: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def size_usd(self) -> Decimal:
        """Position size in USD (absolute value)."""
        return abs(self.size_sol) * self.entry_px
    
    @property
    def unrealized_pnl(self) -> Decimal:
        """Unrealized PnL (positive for short when price drops)."""
        if self.size_sol == 0:
            return Decimal("0")
        price_diff = self.entry_px - self.mark_px  # Short profits when price goes down
        return price_diff * abs(self.size_sol)
    
    @property
    def is_liquidation_risk(self) -> bool:
        """Check if position is at risk of liquidation."""
        # Margin fraction < 0.10 is threshold
        return self.margin_fraction < Decimal("0.10")
    
    @property
    def distance_to_liquidation(self) -> Optional[Decimal]:
        """Distance to liquidation as fraction."""
        if self.liquidation_px is None or self.liquidation_px == 0:
            return None
        
        # For short, liquidation is when price goes up
        if self.mark_px >= self.liquidation_px:
            return Decimal("0")
        
        return (self.liquidation_px - self.mark_px) / self.mark_px


class PositionReference(BaseModel):
    """
    Reference prices captured at position entry for validation.
    
    Used to validate fill prices against expected prices.
    """
    
    asgard_entry_price: Decimal = Field(description="Asgard entry price")
    hyperliquid_entry_price: Decimal = Field(description="Hyperliquid entry price")
    max_acceptable_deviation: Decimal = Field(default=Decimal("0.005"), description="Max 0.5% deviation")
    
    def validate_fills(
        self, 
        asgard_fill_price: Decimal, 
        hyperliquid_fill_price: Decimal
    ) -> "FillValidationResult":
        """
        Validate actual fill prices against reference prices.
        
        Returns FillValidationResult with details on any deviation.
        """
        asgard_deviation = abs(asgard_fill_price - self.asgard_entry_price) / self.asgard_entry_price
        hyperliquid_deviation = abs(hyperliquid_fill_price - self.hyperliquid_entry_price) / self.hyperliquid_entry_price
        
        asgard_within_tolerance = asgard_deviation <= self.max_acceptable_deviation
        hyperliquid_within_tolerance = hyperliquid_deviation <= self.max_acceptable_deviation
        
        return FillValidationResult(
            asgard_fill_price=asgard_fill_price,
            hyperliquid_fill_price=hyperliquid_fill_price,
            asgard_deviation=asgard_deviation,
            hyperliquid_deviation=hyperliquid_deviation,
            asgard_within_tolerance=asgard_within_tolerance,
            hyperliquid_within_tolerance=hyperliquid_within_tolerance,
            both_within_tolerance=asgard_within_tolerance and hyperliquid_within_tolerance,
        )


class FillValidationResult(BaseModel):
    """Result of fill price validation."""
    
    asgard_fill_price: Decimal
    hyperliquid_fill_price: Decimal
    asgard_deviation: Decimal
    hyperliquid_deviation: Decimal
    asgard_within_tolerance: bool
    hyperliquid_within_tolerance: bool
    both_within_tolerance: bool
    
    @property
    def needs_soft_stop(self) -> bool:
        """
        Determine if soft stop is needed.
        
        Soft stop: Re-evaluate profitability at actual prices before unwinding.
        """
        # Trigger soft stop if either leg exceeds tolerance
        return not self.both_within_tolerance


class CombinedPosition(BaseModel):
    """
    Combined delta-neutral position (Asgard long + Hyperliquid short).
    
    This is the main position entity tracked by the system.
    """
    
    # Identification
    position_id: PositionId = Field(description="Unique position ID")
    user_id: Optional[str] = Field(default=None, description="Owner user ID (for multi-tenant)")
    
    # Legs
    asgard: AsgardPosition = Field(description="Long leg on Asgard")
    hyperliquid: HyperliquidPosition = Field(description="Short leg on Hyperliquid")
    
    # Entry reference
    reference: PositionReference = Field(description="Reference prices at entry")
    
    # Opportunity that created this position
    opportunity_id: str = Field(description="ID of originating opportunity")
    
    # Lifecycle
    status: str = Field(default="open", description="open, closing, closed")
    exit_reason: Optional[ExitReason] = None
    exit_time: Optional[datetime] = None
    
    # Performance tracking
    total_funding_received: Decimal = Field(default=Decimal("0"))
    total_funding_paid: Decimal = Field(default=Decimal("0"))
    
    # State machine tracking
    transaction_state: TransactionState = Field(default=TransactionState.IDLE)
    state_history: List[dict] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def is_open(self) -> bool:
        """True if position is currently open."""
        return self.status == "open"
    
    @property
    def is_closed(self) -> bool:
        """True if position is closed."""
        return self.status == "closed"
    
    @property
    def delta(self) -> Decimal:
        """
        Calculate current delta (net exposure).
        
        Delta = Long USD Value - Short USD Value
        Positive delta = net long
        Negative delta = net short
        """
        long_usd = self.asgard.current_value_usd
        short_usd = self.hyperliquid.size_usd
        return long_usd - short_usd
    
    @property
    def delta_ratio(self) -> Decimal:
        """
        Delta as ratio of position size.
        
        0 = perfectly neutral
        """
        position_size = self.asgard.position_size_usd
        if position_size == 0:
            return Decimal("0")
        return self.delta / position_size
    
    @property
    def net_funding_pnl(self) -> Decimal:
        """Net funding PnL (received - paid)."""
        return self.total_funding_received - self.total_funding_paid
    
    @property
    def total_pnl(self) -> Decimal:
        """Total unrealized PnL (both legs + funding)."""
        return self.asgard.pnl_usd + self.hyperliquid.unrealized_pnl + self.net_funding_pnl
    
    @property
    def is_at_risk(self) -> bool:
        """True if either leg is at risk of liquidation."""
        return self.asgard.is_liquidation_risk or self.hyperliquid.is_liquidation_risk
    
    def update_state(self, new_state: TransactionState, metadata: Optional[dict] = None):
        """Update transaction state with history tracking."""
        old_state = self.transaction_state
        self.transaction_state = new_state
        self.updated_at = datetime.utcnow()
        
        self.state_history.append({
            "from": old_state.value,
            "to": new_state.value,
            "timestamp": self.updated_at.isoformat(),
            "metadata": metadata or {},
        })
    
    def to_summary(self) -> dict:
        """Get position summary for logging/display."""
        return {
            "position_id": self.position_id,
            "asset": self.asgard.asset.value,
            "status": self.status,
            "leverage": float(self.asgard.leverage),
            "deployed_usd": float(self.asgard.collateral_usd),
            "long_value_usd": float(self.asgard.current_value_usd),
            "short_value_usd": float(self.hyperliquid.size_usd),
            "delta": float(self.delta),
            "delta_ratio": float(self.delta_ratio),
            "asgard_hf": float(self.asgard.current_health_factor),
            "hyperliquid_mf": float(self.hyperliquid.margin_fraction),
            "total_pnl_usd": float(self.total_pnl),
            "funding_pnl_usd": float(self.net_funding_pnl),
        }
