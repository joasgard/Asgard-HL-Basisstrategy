"""
Funding rate and borrowing rate models.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class FundingRate(BaseModel):
    """Funding rate for a perpetual market."""
    
    timestamp: datetime = Field(description="Timestamp of the funding rate")
    coin: str = Field(description="Coin symbol (e.g., 'SOL')")
    rate_8hr: Decimal = Field(description="8-hour funding rate (e.g., -0.0001)")
    
    # Derived fields
    @property
    def rate_hourly(self) -> Decimal:
        """Hourly funding rate (1/8 of 8hr rate)."""
        return self.rate_8hr / Decimal("8")
    
    @property
    def rate_annual(self) -> Decimal:
        """Annualized funding rate."""
        return self.rate_hourly * Decimal("24") * Decimal("365")
    
    @property
    def is_negative(self) -> bool:
        """True if shorts are paid (rate < 0)."""
        return self.rate_8hr < 0
    
    def projected_annual_yield(self, position_size_usd: Decimal) -> Decimal:
        """Calculate annual yield in USD for a position size."""
        return position_size_usd * self.rate_annual


class BorrowingRate(BaseModel):
    """Borrowing rate for a token on a specific protocol."""
    
    protocol_id: int = Field(description="Protocol ID (0-3)")
    token_mint: str = Field(description="Token mint address")
    borrowing_apy: Decimal = Field(description="Annual borrowing rate")
    
    @field_validator("protocol_id")
    @classmethod
    def validate_protocol(cls, v: int) -> int:
        if not 0 <= v <= 3:
            raise ValueError("protocol_id must be 0-3")
        return v


class LendingRate(BaseModel):
    """Lending rate for a token on a specific protocol."""
    
    protocol_id: int = Field(description="Protocol ID (0-3)")
    token_mint: str = Field(description="Token mint address")
    lending_apy: Decimal = Field(description="Annual lending rate")
    
    @field_validator("protocol_id")
    @classmethod
    def validate_protocol(cls, v: int) -> int:
        if not 0 <= v <= 3:
            raise ValueError("protocol_id must be 0-3")
        return v


class AsgardRates(BaseModel):
    """Combined lending and borrowing rates from Asgard."""
    
    protocol_id: int = Field(description="Protocol ID")
    token_a_mint: str = Field(description="Long token mint (SOL/LST)")
    token_b_mint: str = Field(description="Borrow token mint (USDC)")
    token_a_lending_apy: Decimal = Field(description="Lending APY for token A")
    token_b_borrowing_apy: Decimal = Field(description="Borrowing APY for token B")
    token_b_max_borrow_capacity: Decimal = Field(description="Max borrow capacity in USD")
    
    def calculate_net_carry_apy(
        self, 
        leverage: Decimal, 
        deployed_capital_usd: Decimal
    ) -> Decimal:
        """
        Calculate net carry APY on deployed capital.
        
        Formula: Net_Carry = (Leverage × Lending) - ((Leverage - 1) × Borrowing)
                 Net_Carry_APY = Net_Carry / Deployed_Capital
        
        Args:
            leverage: Position leverage (e.g., 3.0)
            deployed_capital_usd: Capital deployed in USD
        
        Returns:
            Net carry APY as Decimal
        """
        position_size = deployed_capital_usd * leverage
        borrowed_amount = position_size - deployed_capital_usd
        
        lending_yield = position_size * self.token_a_lending_apy
        borrowing_cost = borrowed_amount * self.token_b_borrowing_apy
        
        net_carry = lending_yield - borrowing_cost
        
        if deployed_capital_usd == 0:
            return Decimal("0")
        
        return net_carry / deployed_capital_usd
    
    def has_sufficient_capacity(
        self, 
        position_size_usd: Decimal, 
        leverage: Decimal,
        safety_margin: Decimal = Decimal("1.2")
    ) -> bool:
        """
        Check if protocol has sufficient borrow capacity.
        
        Args:
            position_size_usd: Total position size in USD
            leverage: Position leverage
            safety_margin: Safety multiplier (default 1.2 = 20% buffer)
        
        Returns:
            True if capacity is sufficient
        """
        borrowed_amount = position_size_usd * (leverage - 1) / leverage
        required_capacity = borrowed_amount * safety_margin
        
        return self.token_b_max_borrow_capacity >= required_capacity


class FundingPrediction(BaseModel):
    """Predicted funding rate based on current premium."""
    
    coin: str
    current_premium: Decimal = Field(description="1-hour TWAP premium")
    interest_rate: Decimal = Field(description="Base interest rate")
    predicted_rate_8hr: Decimal
    confidence: Decimal = Field(default=Decimal("0.5"), description="Prediction confidence 0-1")
    
    @property
    def predicted_rate_hourly(self) -> Decimal:
        """Predicted hourly rate."""
        return self.predicted_rate_8hr / Decimal("8")
    
    @property
    def is_predicted_negative(self) -> bool:
        """True if predicted rate indicates shorts will be paid."""
        return self.predicted_rate_8hr < 0
