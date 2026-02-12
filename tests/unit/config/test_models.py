"""
Tests for data models.
"""
from datetime import datetime
from decimal import Decimal

import pytest

from shared.models.common import Asset, Protocol, TransactionState, Chain
from shared.models.funding import FundingRate, AsgardRates, BorrowingRate, LendingRate
from shared.models.opportunity import ArbitrageOpportunity, OpportunityScore, OpportunityFilter
from shared.models.position import (
    AsgardPosition, HyperliquidPosition, CombinedPosition, PositionReference
)


class TestFundingModels:
    """Test funding rate models."""
    
    def test_funding_rate_calculation(self):
        """Test funding rate calculations."""
        rate = FundingRate(
            timestamp=datetime.utcnow(),
            coin="SOL",
            rate_8hr=Decimal("-0.0008"),  # -0.08% per 8 hours
        )
        
        # Hourly rate should be 1/8 of 8hr rate
        assert rate.rate_hourly == Decimal("-0.0001")
        
        # Annual rate: -0.0001 * 24 * 365 = -0.876
        assert rate.rate_annual == Decimal("-0.876")
        
        # Should be negative
        assert rate.is_negative is True
        
        # Projected annual yield for $150k position
        yield_usd = rate.projected_annual_yield(Decimal("150000"))
        assert yield_usd == Decimal("150000") * Decimal("-0.876")
    
    def test_net_carry_calculation(self):
        """Test net carry calculation on deployed capital."""
        rates = AsgardRates(
            protocol_id=0,  # Marginfi
            token_a_mint="So11111111111111111111111111111111111111112",
            token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            token_a_lending_apy=Decimal("0.06"),  # 6% lending
            token_b_borrowing_apy=Decimal("0.05"),  # 5% borrowing
            token_b_max_borrow_capacity=Decimal("1000000"),
        )
        
        # 3x leverage, $100k deployed
        # Position size: $300k, Borrowed: $200k
        # Lending yield: $300k * 6% = $18k
        # Borrowing cost: $200k * 5% = $10k
        # Net carry: $8k / $100k = 8%
        net_carry = rates.calculate_net_carry_apy(
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("100000")
        )
        
        assert net_carry == Decimal("0.08")  # 8%
    
    def test_capacity_check(self):
        """Test protocol capacity checking."""
        rates = AsgardRates(
            protocol_id=0,
            token_a_mint="So11111111111111111111111111111111111111112",
            token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            token_a_lending_apy=Decimal("0.05"),
            token_b_borrowing_apy=Decimal("0.08"),
            token_b_max_borrow_capacity=Decimal("50000"),  # $50k capacity
        )
        
        # $150k position, 3x leverage = borrow $100k
        # With 1.2 safety margin: need $120k capacity
        assert rates.has_sufficient_capacity(
            position_size_usd=Decimal("150000"),
            leverage=Decimal("3"),
            safety_margin=Decimal("1.2")
        ) is False  # $50k < $120k
        
        # $75k position, 3x leverage = borrow $50k
        # With 1.2 safety margin: need $60k capacity
        assert rates.has_sufficient_capacity(
            position_size_usd=Decimal("75000"),
            leverage=Decimal("3"),
            safety_margin=Decimal("1.2")
        ) is False  # $50k < $60k
        
        # Without safety margin
        assert rates.has_sufficient_capacity(
            position_size_usd=Decimal("75000"),
            leverage=Decimal("3"),
            safety_margin=Decimal("1.0")
        ) is True  # $50k == $50k


class TestOpportunityModel:
    """Test opportunity detection model."""
    
    def test_opportunity_scoring(self):
        """Test opportunity scoring calculation."""
        score = OpportunityScore(
            funding_apy=Decimal("0.15"),  # 15% from funding
            net_carry_apy=Decimal("0.08"),  # 8% from carry
            lst_staking_apy=Decimal("0.075"),  # 7.5% from LST
        )
        
        # Gross should sum all yield sources
        assert score.total_gross_apy == Decimal("0.305")  # 30.5%
        
        # Without costs, net equals gross
        assert score.total_net_apy == Decimal("0.305")
        assert score.is_profitable is True
    
    def test_opportunity_entry_criteria(self):
        """Test entry criteria validation."""
        from shared.models.common import Asset, Protocol
        
        asgard_rates = AsgardRates(
            protocol_id=0,
            token_a_mint="So11111111111111111111111111111111111111112",
            token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            token_a_lending_apy=Decimal("0.05"),
            token_b_borrowing_apy=Decimal("0.08"),
            token_b_max_borrow_capacity=Decimal("1000000"),
        )
        
        funding = FundingRate(
            timestamp=datetime.utcnow(),
            coin="SOL",
            rate_8hr=Decimal("-0.0008"),  # Negative = shorts paid
        )
        
        score = OpportunityScore(
            funding_apy=Decimal("0.15"),
            net_carry_apy=Decimal("0.08"),
        )
        
        # Valid opportunity
        opp = ArbitrageOpportunity(
            id="test-opp-1",
            asset=Asset.SOL,
            selected_protocol=Protocol.MARGINFI,
            asgard_rates=asgard_rates,
            current_funding=funding,
            funding_volatility=Decimal("0.3"),  # 30% < 50%
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("100000"),
            position_size_usd=Decimal("300000"),
            score=score,
            price_deviation=Decimal("0.002"),  # 0.2% < 0.5%
            preflight_checks_passed=True,
        )
        
        assert opp.meets_entry_criteria is True
        
        # Test with positive funding (should fail)
        bad_funding = FundingRate(
            timestamp=datetime.utcnow(),
            coin="SOL",
            rate_8hr=Decimal("0.0008"),  # Positive = shorts pay
        )
        
        opp_bad = ArbitrageOpportunity(
            id="test-opp-2",
            asset=Asset.SOL,
            selected_protocol=Protocol.MARGINFI,
            asgard_rates=asgard_rates,
            current_funding=bad_funding,
            funding_volatility=Decimal("0.3"),
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("100000"),
            position_size_usd=Decimal("300000"),
            score=score,
            price_deviation=Decimal("0.002"),
            preflight_checks_passed=True,
        )
        
        assert opp_bad.meets_entry_criteria is False
    
    def test_opportunity_leverage_validation(self):
        """Test leverage bounds validation."""
        from shared.models.common import Asset, Protocol
        
        asgard_rates = AsgardRates(
            protocol_id=0,
            token_a_mint="So11111111111111111111111111111111111111112",
            token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            token_a_lending_apy=Decimal("0.05"),
            token_b_borrowing_apy=Decimal("0.08"),
            token_b_max_borrow_capacity=Decimal("1000000"),
        )
        
        funding = FundingRate(
            timestamp=datetime.utcnow(),
            coin="SOL",
            rate_8hr=Decimal("-0.0008"),
        )
        
        score = OpportunityScore(funding_apy=Decimal("0.1"), net_carry_apy=Decimal("0.05"))
        
        # Valid leverage
        opp = ArbitrageOpportunity(
            id="test",
            asset=Asset.SOL,
            selected_protocol=Protocol.MARGINFI,
            asgard_rates=asgard_rates,
            current_funding=funding,
            funding_volatility=Decimal("0.3"),
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("100000"),
            position_size_usd=Decimal("300000"),
            score=score,
            price_deviation=Decimal("0.001"),
        )
        assert opp.leverage == Decimal("3")
        
        # Invalid leverage (too high)
        with pytest.raises(ValueError, match="leverage must be between 1.1 and 4"):
            ArbitrageOpportunity(
                id="test",
                asset=Asset.SOL,
                selected_protocol=Protocol.MARGINFI,
                asgard_rates=asgard_rates,
                current_funding=funding,
                funding_volatility=Decimal("0.3"),
                leverage=Decimal("5"),  # Too high
                deployed_capital_usd=Decimal("100000"),
                position_size_usd=Decimal("500000"),
                score=score,
                price_deviation=Decimal("0.001"),
            )
        
        # Invalid leverage (too low - below 1.1)
        with pytest.raises(ValueError, match="leverage must be between 1.1 and 4"):
            ArbitrageOpportunity(
                id="test",
                asset=Asset.SOL,
                selected_protocol=Protocol.MARGINFI,
                asgard_rates=asgard_rates,
                current_funding=funding,
                funding_volatility=Decimal("0.3"),
                leverage=Decimal("1.0"),  # Too low
                deployed_capital_usd=Decimal("100000"),
                position_size_usd=Decimal("500000"),
                score=score,
                price_deviation=Decimal("0.001"),
            )
        
        # Valid leverage at new minimum (1.1x)
        opp_low = ArbitrageOpportunity(
            id="test",
            asset=Asset.SOL,
            selected_protocol=Protocol.MARGINFI,
            asgard_rates=asgard_rates,
            current_funding=funding,
            funding_volatility=Decimal("0.3"),
            leverage=Decimal("1.1"),  # New minimum
            deployed_capital_usd=Decimal("100000"),
            position_size_usd=Decimal("500000"),
            score=score,
            price_deviation=Decimal("0.001"),
        )
        assert opp_low.leverage == Decimal("1.1")


class TestPositionModels:
    """Test position models."""
    
    def test_asgard_position_health(self):
        """Test Asgard position health factor checks."""
        pos = AsgardPosition(
            position_pda="test-pda",
            intent_id="test-intent",
            asset=Asset.SOL,
            protocol=Protocol.MARGINFI,
            collateral_usd=Decimal("100000"),
            position_size_usd=Decimal("300000"),
            leverage=Decimal("3"),
            token_a_amount=Decimal("1500"),
            token_b_borrowed=Decimal("200000"),
            entry_price_token_a=Decimal("200"),
            current_health_factor=Decimal("0.25"),
            current_token_a_price=Decimal("205"),
        )
        
        # HF 0.25 > 0.20, not at risk
        assert pos.is_liquidation_risk is False
        assert pos.is_critical_liquidation_risk is False
        
        # Update to critical
        pos.current_health_factor = Decimal("0.08")
        assert pos.is_liquidation_risk is True
        assert pos.is_critical_liquidation_risk is True
    
    def test_hyperliquid_position_pnl(self):
        """Test Hyperliquid position PnL calculation."""
        pos = HyperliquidPosition(
            size_sol=Decimal("-1500"),  # Short 1500 SOL
            entry_px=Decimal("200"),
            leverage=Decimal("3"),
            margin_used=Decimal("100000"),
            margin_fraction=Decimal("0.15"),
            account_value=Decimal("100000"),
            mark_px=Decimal("190"),  # Price dropped $10
        )
        
        # Position size in USD
        assert pos.size_usd == Decimal("300000")
        
        # Short profits when price goes down
        # Price dropped from $200 to $190 = $10 profit per SOL
        # 1500 SOL * $10 = $15,000 profit
        assert pos.unrealized_pnl == Decimal("15000")
    
    def test_combined_position_delta(self):
        """Test combined position delta calculation."""
        asgard_pos = AsgardPosition(
            position_pda="test-pda",
            intent_id="test-intent",
            asset=Asset.SOL,
            protocol=Protocol.MARGINFI,
            collateral_usd=Decimal("100000"),
            position_size_usd=Decimal("300000"),
            leverage=Decimal("3"),
            token_a_amount=Decimal("1500"),
            token_b_borrowed=Decimal("200000"),
            entry_price_token_a=Decimal("200"),
            current_health_factor=Decimal("0.25"),
            current_token_a_price=Decimal("200"),
        )
        
        hyperliquid_pos = HyperliquidPosition(
            size_sol=Decimal("-1500"),  # Short 1500 SOL
            entry_px=Decimal("200"),
            leverage=Decimal("3"),
            margin_used=Decimal("100000"),
            margin_fraction=Decimal("0.15"),
            account_value=Decimal("100000"),
            mark_px=Decimal("200"),
        )
        
        ref = PositionReference(
            asgard_entry_price=Decimal("200"),
            hyperliquid_entry_price=Decimal("200"),
        )
        
        combined = CombinedPosition(
            position_id="test-pos-1",
            asgard=asgard_pos,
            hyperliquid=hyperliquid_pos,
            reference=ref,
            opportunity_id="test-opp-1",
        )
        
        # Long $300k, Short $300k = delta 0 (neutral)
        assert combined.delta == Decimal("0")
        assert combined.delta_ratio == Decimal("0")
        
        # Now price moves: SOL goes to $210
        asgard_pos.current_token_a_price = Decimal("210")
        hyperliquid_pos.mark_px = Decimal("210")
        
        # Long value: 1500 * $210 = $315k
        # Short value: 1500 * $200 (entry) = $300k
        # Delta: $315k - $300k = $15k (net long bias)
        assert combined.delta == Decimal("15000")
    
    def test_position_reference_validation(self):
        """Test fill price validation against reference."""
        ref = PositionReference(
            asgard_entry_price=Decimal("200"),
            hyperliquid_entry_price=Decimal("200"),
            max_acceptable_deviation=Decimal("0.005"),  # 0.5%
        )
        
        # Within tolerance
        result = ref.validate_fills(
            asgard_fill_price=Decimal("200.5"),  # 0.25% deviation
            hyperliquid_fill_price=Decimal("200.8"),  # 0.4% deviation
        )
        
        assert result.both_within_tolerance is True
        assert result.needs_soft_stop is False
        
        # Outside tolerance
        result_bad = ref.validate_fills(
            asgard_fill_price=Decimal("205"),  # 2.5% deviation
            hyperliquid_fill_price=Decimal("200"),
        )
        
        assert result_bad.both_within_tolerance is False
        assert result_bad.needs_soft_stop is True


class TestEnums:
    """Test common enums."""
    
    def test_asset_enum(self):
        """Test all assets defined."""
        assert Asset.SOL.value == "SOL"
        assert Asset.JITOSOL.value == "jitoSOL"
        assert Asset.JUPSOL.value == "jupSOL"
        assert Asset.INF.value == "INF"
        assert len(Asset) == 4
    
    def test_protocol_enum(self):
        """Test protocol ordering matches tie-breaker."""
        assert Protocol.MARGINFI.value == 0
        assert Protocol.KAMINO.value == 1
        assert Protocol.SOLEND.value == 2
        assert Protocol.DRIFT.value == 3
    
    def test_transaction_state_enum(self):
        """Test transaction state machine states."""
        states = [
            TransactionState.IDLE,
            TransactionState.BUILDING,
            TransactionState.BUILT,
            TransactionState.SIGNING,
            TransactionState.SIGNED,
            TransactionState.SUBMITTING,
            TransactionState.SUBMITTED,
            TransactionState.CONFIRMED,
            TransactionState.FAILED,
        ]
        assert len(states) == 9
