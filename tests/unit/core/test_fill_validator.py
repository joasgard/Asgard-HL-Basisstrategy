"""
Tests for Fill Validation module.

These tests verify:
- Fill validation logic
- Deviation calculation
- Soft stop logic (re-evaluate profitability)
- Hard stop logic (unwind if unprofitable)
- Price impact calculations
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.config.assets import Asset
from bot.core.fill_validator import (
    FillInfo,
    FillValidator,
    PositionReference,
    ValidationResult,
)
from shared.models.common import Protocol
from shared.models.funding import AsgardRates, FundingRate
from shared.models.opportunity import ArbitrageOpportunity, OpportunityScore


# Fixtures
@pytest.fixture
def sample_opportunity():
    """Create a sample arbitrage opportunity."""
    base_time = datetime.utcnow()
    
    return ArbitrageOpportunity(
        id="test-opp-1",
        asset=Asset.SOL,
        selected_protocol=Protocol.MARGINFI,
        asgard_rates=AsgardRates(
            protocol_id=0,
            token_a_mint="So11111111111111111111111111111111111111112",
            token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            token_a_lending_apy=Decimal("0.05"),
            token_b_borrowing_apy=Decimal("0.08"),
            token_b_max_borrow_capacity=Decimal("1000000"),
        ),
        current_funding=FundingRate(
            timestamp=base_time,
            coin="SOL",
            rate_8hr=Decimal("-0.0001"),
        ),
        funding_volatility=Decimal("0.2"),
        leverage=Decimal("3"),
        deployed_capital_usd=Decimal("50000"),
        position_size_usd=Decimal("150000"),
        score=OpportunityScore(
            funding_apy=Decimal("0.1095"),  # 10.95% from funding
            net_carry_apy=Decimal("-0.01"),  # -1% net carry
            lst_staking_apy=Decimal("0"),
        ),
        price_deviation=Decimal("0.001"),
    )


@pytest.fixture
def valid_asgard_fill():
    """Create a valid Asgard fill (no deviation)."""
    return FillInfo(
        venue="asgard",
        side="long",
        size_usd=Decimal("150000"),
        filled_price=Decimal("100"),
        expected_price=Decimal("100"),
    )


@pytest.fixture
def valid_hyperliquid_fill():
    """Create a valid Hyperliquid fill (no deviation)."""
    return FillInfo(
        venue="hyperliquid",
        side="short",
        size_usd=Decimal("150000"),
        filled_price=Decimal("100.5"),
        expected_price=Decimal("100.5"),
    )


@pytest.fixture
def deviated_asgard_fill():
    """Create an Asgard fill with 1% deviation."""
    return FillInfo(
        venue="asgard",
        side="long",
        size_usd=Decimal("150000"),
        filled_price=Decimal("101"),  # 1% higher than expected
        expected_price=Decimal("100"),
    )


@pytest.fixture
def deviated_hyperliquid_fill():
    """Create a Hyperliquid fill with 1% deviation."""
    return FillInfo(
        venue="hyperliquid",
        side="short",
        size_usd=Decimal("150000"),
        filled_price=Decimal("99.5"),  # ~1% lower than expected
        expected_price=Decimal("100.5"),
    )


class TestFillValidatorInit:
    """Tests for FillValidator initialization."""
    
    def test_init_default(self):
        """Test initialization with default values."""
        validator = FillValidator()
        assert validator.max_deviation == FillValidator.MAX_FILL_DEVIATION
        assert validator.max_deviation == Decimal("0.005")  # 0.5%
    
    def test_init_custom_deviation(self):
        """Test initialization with custom deviation."""
        validator = FillValidator(max_deviation=Decimal("0.01"))
        assert validator.max_deviation == Decimal("0.01")


class TestValidateFills:
    """Tests for fill validation."""
    
    @pytest.mark.asyncio
    async def test_valid_fills_no_deviation(
        self, sample_opportunity, valid_asgard_fill, valid_hyperliquid_fill
    ):
        """Test validation with perfect fills."""
        validator = FillValidator()
        
        result = await validator.validate_fills(
            asgard_fill=valid_asgard_fill,
            hyperliquid_fill=valid_hyperliquid_fill,
            expected_spread=Decimal("0.5"),
            opportunity=sample_opportunity,
        )
        
        assert result.is_valid is True
        assert result.action == "proceed"
        assert result.soft_stop_triggered is False
        assert result.should_unwind is False
    
    @pytest.mark.asyncio
    async def test_soft_stop_still_profitable(
        self, sample_opportunity, deviated_asgard_fill, valid_hyperliquid_fill
    ):
        """Test soft stop when position is still profitable."""
        validator = FillValidator()
        
        result = await validator.validate_fills(
            asgard_fill=deviated_asgard_fill,
            hyperliquid_fill=valid_hyperliquid_fill,
            expected_spread=Decimal("0.5"),
            opportunity=sample_opportunity,
        )
        
        # Should trigger soft stop (> 0.5% deviation)
        assert result.soft_stop_triggered is True
        assert result.action == "soft_stop"
        # Should NOT unwind (still profitable)
        assert result.should_unwind is False
        assert result.is_valid is True  # Still valid
    
    @pytest.mark.asyncio
    async def test_hard_stop_unprofitable(
        self, sample_opportunity, deviated_asgard_fill, deviated_hyperliquid_fill
    ):
        """Test hard stop when position becomes unprofitable."""
        # Create opportunity with very small margin that will become negative
        sample_opportunity.score = OpportunityScore(
            funding_apy=Decimal("0.005"),  # Only 0.5% APY - will go negative with 1% impact
            net_carry_apy=Decimal("0"),
        )
        
        validator = FillValidator()
        
        result = await validator.validate_fills(
            asgard_fill=deviated_asgard_fill,
            hyperliquid_fill=deviated_hyperliquid_fill,
            expected_spread=Decimal("0.5"),
            opportunity=sample_opportunity,
        )
        
        # Large deviations (1% each) should make it unprofitable
        assert result.soft_stop_triggered is True
        assert result.action == "hard_stop"
        assert result.should_unwind is True
        assert result.is_valid is False
        assert result.apy_at_fills < 0
    
    @pytest.mark.asyncio
    async def test_deviation_calculation(
        self, sample_opportunity, deviated_asgard_fill, valid_hyperliquid_fill
    ):
        """Test deviation calculation."""
        validator = FillValidator()
        
        result = await validator.validate_fills(
            asgard_fill=deviated_asgard_fill,
            hyperliquid_fill=valid_hyperliquid_fill,
            expected_spread=Decimal("0.5"),
            opportunity=sample_opportunity,
        )
        
        # Asgard deviation: (101 - 100) / 100 = 1%
        assert result.asgard_deviation == Decimal("0.01")
        # Hyperliquid deviation: 0%
        assert result.hyperliquid_deviation == Decimal("0")
        # Max deviation is 1%
        assert result.max_deviation == Decimal("0.01")


class TestValidateQuick:
    """Tests for quick validation."""
    
    def test_quick_validation_proceed(self):
        """Test quick validation when within threshold."""
        validator = FillValidator()
        
        result = validator.validate_quick(
            asgard_fill_price=Decimal("100"),
            hyperliquid_fill_price=Decimal("100.5"),
            asgard_expected=Decimal("100"),
            hyperliquid_expected=Decimal("100.5"),
        )
        
        assert result.is_valid is True
        assert result.action == "proceed"
        assert result.soft_stop_triggered is False
    
    def test_quick_validation_soft_stop(self):
        """Test quick validation triggers soft stop."""
        validator = FillValidator()
        
        result = validator.validate_quick(
            asgard_fill_price=Decimal("101"),  # 1% deviation
            hyperliquid_fill_price=Decimal("100"),
            asgard_expected=Decimal("100"),
            hyperliquid_expected=Decimal("100"),
        )
        
        assert result.action == "soft_stop"
        assert result.soft_stop_triggered is True
        assert result.max_deviation == Decimal("0.01")


class TestFillInfo:
    """Tests for FillInfo dataclass."""
    
    def test_fill_info_calculates_slippage(self):
        """Test that slippage is calculated automatically."""
        fill = FillInfo(
            venue="asgard",
            side="long",
            size_usd=Decimal("150000"),
            filled_price=Decimal("101"),
            expected_price=Decimal("100"),
        )
        
        # Slippage: (101 - 100) / 100 * 10000 = 100 bps (1%)
        assert fill.slippage_bps == Decimal("100")
    
    def test_fill_info_zero_expected_price(self):
        """Test handling of zero expected price."""
        fill = FillInfo(
            venue="asgard",
            side="long",
            size_usd=Decimal("150000"),
            filled_price=Decimal("100"),
            expected_price=Decimal("0"),
            slippage_bps=Decimal("0"),  # Pre-set to avoid division by zero
        )
        
        assert fill.slippage_bps == Decimal("0")
    
    def test_fill_info_with_fees(self):
        """Test FillInfo with fees."""
        fill = FillInfo(
            venue="hyperliquid",
            side="short",
            size_usd=Decimal("150000"),
            filled_price=Decimal("100"),
            expected_price=Decimal("100"),
            fees_usd=Decimal("15"),  # $15 fees
        )
        
        assert fill.fees_usd == Decimal("15")


class TestPositionReference:
    """Tests for PositionReference dataclass."""
    
    def test_price_spread_calculation(self):
        """Test price spread calculation."""
        ref = PositionReference(
            asgard_entry_price=Decimal("100"),
            hyperliquid_entry_price=Decimal("100.5"),
        )
        
        assert ref.price_spread == Decimal("0.5")
    
    def test_avg_price_calculation(self):
        """Test average price calculation."""
        ref = PositionReference(
            asgard_entry_price=Decimal("100"),
            hyperliquid_entry_price=Decimal("102"),
        )
        
        assert ref.avg_price == Decimal("101")
    
    def test_default_threshold(self):
        """Test default max acceptable deviation."""
        ref = PositionReference(
            asgard_entry_price=Decimal("100"),
            hyperliquid_entry_price=Decimal("100"),
        )
        
        assert ref.max_acceptable_deviation == Decimal("0.005")


class TestPriceImpactCalculation:
    """Tests for price impact calculation."""
    
    def test_price_impact_long_worse_fill(self):
        """Test price impact for long with worse fill."""
        validator = FillValidator()
        
        # Long filled higher than expected (worse)
        impact = validator._calculate_price_impact(
            filled_price=Decimal("101"),
            expected_price=Decimal("100"),
            is_long=True,
        )
        
        # Impact should be 1%
        assert impact == Decimal("0.01")
    
    def test_price_impact_long_better_fill(self):
        """Test price impact for long with better fill."""
        validator = FillValidator()
        
        # Long filled lower than expected (better)
        impact = validator._calculate_price_impact(
            filled_price=Decimal("99"),
            expected_price=Decimal("100"),
            is_long=True,
        )
        
        # No negative impact for better fills
        assert impact == Decimal("0")
    
    def test_price_impact_short_worse_fill(self):
        """Test price impact for short with worse fill."""
        validator = FillValidator()
        
        # Short filled lower than expected (worse)
        impact = validator._calculate_price_impact(
            filled_price=Decimal("99"),
            expected_price=Decimal("100"),
            is_long=False,
        )
        
        # Impact should be 1%
        assert impact == Decimal("0.01")
    
    def test_price_impact_short_better_fill(self):
        """Test price impact for short with better fill."""
        validator = FillValidator()
        
        # Short filled higher than expected (better)
        impact = validator._calculate_price_impact(
            filled_price=Decimal("101"),
            expected_price=Decimal("100"),
            is_long=False,
        )
        
        # No negative impact for better fills
        assert impact == Decimal("0")


class TestDeviationCalculation:
    """Tests for deviation calculation."""
    
    def test_deviation_zero(self):
        """Test deviation with same prices."""
        validator = FillValidator()
        dev = validator._calculate_deviation(
            Decimal("100"),
            Decimal("100"),
        )
        assert dev == Decimal("0")
    
    def test_deviation_positive(self):
        """Test deviation with different prices."""
        validator = FillValidator()
        dev = validator._calculate_deviation(
            Decimal("101"),
            Decimal("100"),
        )
        assert dev == Decimal("0.01")  # 1%
    
    def test_deviation_zero_expected(self):
        """Test deviation with zero expected price."""
        validator = FillValidator()
        dev = validator._calculate_deviation(
            Decimal("100"),
            Decimal("0"),
        )
        assert dev == Decimal("0")


class TestSoftStopReason:
    """Tests for soft stop reason generation."""
    
    def test_both_fills_exceeded(self):
        """Test reason when both fills exceed threshold."""
        validator = FillValidator()
        reason = validator._get_soft_stop_reason(
            asgard_dev=Decimal("0.01"),
            hyperliquid_dev=Decimal("0.008"),
            max_dev=Decimal("0.01"),
        )
        
        assert "Both fills exceeded" in reason
    
    def test_only_asgard_exceeded(self):
        """Test reason when only Asgard exceeds threshold."""
        validator = FillValidator()
        reason = validator._get_soft_stop_reason(
            asgard_dev=Decimal("0.01"),
            hyperliquid_dev=Decimal("0.001"),
            max_dev=Decimal("0.01"),
        )
        
        assert "Asgard fill exceeded" in reason
    
    def test_only_hyperliquid_exceeded(self):
        """Test reason when only Hyperliquid exceeds threshold."""
        validator = FillValidator()
        reason = validator._get_soft_stop_reason(
            asgard_dev=Decimal("0.001"),
            hyperliquid_dev=Decimal("0.01"),
            max_dev=Decimal("0.01"),
        )
        
        assert "Hyperliquid fill exceeded" in reason


class TestCreatePositionReference:
    """Tests for creating position reference."""
    
    def test_create_from_consensus(self):
        """Test creating PositionReference from ConsensusResult."""
        from bot.core.price_consensus import ConsensusResult
        
        validator = FillValidator()
        
        consensus = ConsensusResult(
            asgard_price=Decimal("100"),
            hyperliquid_price=Decimal("100.5"),
            price_deviation=Decimal("0.005"),
            deviation_percent=Decimal("0.005"),
            asset=Asset.SOL,
            is_within_threshold=True,
            threshold=Decimal("0.005"),
        )
        
        ref = validator.create_position_reference(consensus)
        
        assert ref.asgard_entry_price == Decimal("100")
        assert ref.hyperliquid_entry_price == Decimal("100.5")
        assert ref.max_acceptable_deviation == Decimal("0.005")
        assert ref.timestamp is not None


class TestValidationResult:
    """Tests for ValidationResult dataclass."""
    
    def test_to_summary(self):
        """Test summary dict generation."""
        result = ValidationResult(
            is_valid=True,
            action="proceed",
            max_deviation=Decimal("0.002"),
            apy_at_fills=Decimal("0.10"),
            soft_stop_triggered=False,
            should_unwind=False,
        )
        
        summary = result.to_summary()
        
        assert summary["is_valid"] is True
        assert summary["action"] == "proceed"
        assert summary["max_deviation"] == 0.002
        assert summary["max_deviation_bps"] == 20.0  # 0.2% = 20 bps
        assert summary["apy_at_fills"] == 0.10
        assert summary["soft_stop_triggered"] is False


class TestRecalculateAPY:
    """Tests for APY recalculation at fills."""
    
    @pytest.mark.asyncio
    async def test_apy_recalculation_with_impact(
        self, sample_opportunity, deviated_asgard_fill, valid_hyperliquid_fill
    ):
        """Test APY recalculation with price impact."""
        validator = FillValidator()
        
        result = await validator.validate_fills(
            asgard_fill=deviated_asgard_fill,
            hyperliquid_fill=valid_hyperliquid_fill,
            expected_spread=Decimal("0.5"),
            opportunity=sample_opportunity,
        )
        
        # APY should be reduced due to 1% price impact on long
        original_apy = sample_opportunity.total_expected_apy
        assert result.apy_at_fills < original_apy
    
    @pytest.mark.asyncio
    async def test_apy_recalculation_no_impact(
        self, sample_opportunity, valid_asgard_fill, valid_hyperliquid_fill
    ):
        """Test APY recalculation with no price impact."""
        validator = FillValidator()
        
        result = await validator.validate_fills(
            asgard_fill=valid_asgard_fill,
            hyperliquid_fill=valid_hyperliquid_fill,
            expected_spread=Decimal("0.5"),
            opportunity=sample_opportunity,
        )
        
        # APY should remain same with no deviation
        original_apy = sample_opportunity.total_expected_apy
        assert result.apy_at_fills == original_apy
