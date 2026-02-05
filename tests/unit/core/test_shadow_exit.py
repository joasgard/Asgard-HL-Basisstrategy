"""Tests for ShadowTrader exit logging functionality."""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta

from src.core.shadow import (
    ShadowTrader, ShadowPosition, ShadowPositionStatus,
    ShadowEntry, ShadowExit
)
from src.models.opportunity import ArbitrageOpportunity, OpportunityScore
from src.models.common import Asset, Protocol, ExitReason
from src.models.funding import FundingRate, AsgardRates


@pytest.fixture
def shadow_trader():
    """Create a fresh ShadowTrader instance."""
    return ShadowTrader()


@pytest.fixture
def sample_opportunity():
    """Create a sample arbitrage opportunity."""
    return ArbitrageOpportunity(
        id="opp_12345",
        asset=Asset.SOL,
        selected_protocol=Protocol.KAMINO,
        asgard_rates=AsgardRates(
            protocol_id=1,
            token_a_mint="So11111111111111111111111111111111111111112",
            token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            token_a_lending_apy=Decimal("0.05"),
            token_b_borrowing_apy=Decimal("0.08"),
            token_b_max_borrow_capacity=Decimal("1000000"),
        ),
        hyperliquid_coin="SOL",
        current_funding=FundingRate(
            timestamp=datetime.utcnow(),
            coin="SOL",
            rate_8hr=Decimal("-0.0003"),
        ),
        predicted_funding=FundingRate(
            timestamp=datetime.utcnow(),
            coin="SOL",
            rate_8hr=Decimal("-0.00025"),
        ),
        funding_volatility=Decimal("0.1"),
        leverage=Decimal("3"),
        deployed_capital_usd=Decimal("10000"),
        position_size_usd=Decimal("30000"),
        score=OpportunityScore(
            funding_apy=Decimal("0.25"),
            net_carry_apy=Decimal("0.02"),
            lst_staking_apy=Decimal("0"),
            estimated_gas_cost_apy=Decimal("0.001"),
            estimated_slippage_apy=Decimal("0.005"),
        ),
        price_deviation=Decimal("0.001"),
        preflight_checks_passed=True,
    )


@pytest.fixture
async def open_position(shadow_trader, sample_opportunity):
    """Create and return an open shadow position."""
    return await shadow_trader.shadow_entry(sample_opportunity)


class TestShadowExitBasic:
    """Test basic shadow exit functionality."""
    
    @pytest.mark.asyncio
    async def test_shadow_exit_basic(self, shadow_trader, sample_opportunity):
        """Test basic shadow exit closes position."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        exit_record = await shadow_trader.shadow_exit(position, "funding_flip")
        
        assert exit_record is not None
        assert position.status == ShadowPositionStatus.CLOSED
        assert position.is_closed is True
        assert position.is_open is False
    
    @pytest.mark.asyncio
    async def test_shadow_exit_reason_recorded(self, shadow_trader, sample_opportunity):
        """Test exit reason is recorded."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        exit_record = await shadow_trader.shadow_exit(position, "funding_flip")
        
        assert exit_record.reason == "funding_flip"
        assert position.exit_reason == "funding_flip"
    
    @pytest.mark.asyncio
    async def test_shadow_exit_creates_exit_record(self, shadow_trader, sample_opportunity):
        """Test shadow exit creates exit record."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        await shadow_trader.shadow_exit(position, "manual")
        
        exits = shadow_trader.get_exit_history()
        assert len(exits) == 1
        assert exits[0].position_id == position.position_id
    
    @pytest.mark.asyncio
    async def test_shadow_exit_stores_in_position(self, shadow_trader, sample_opportunity):
        """Test exit record is stored in position."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        exit_record = await shadow_trader.shadow_exit(position, "health_factor")
        
        assert position.exit_record is not None
        assert position.exit_record == exit_record


class TestShadowExitPnLCalculation:
    """Test PnL calculation during shadow exit."""
    
    @pytest.mark.asyncio
    async def test_shadow_exit_zero_pnl(self, shadow_trader, sample_opportunity):
        """Test exit with no price change results in zero position PnL."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        
        assert exit_record.position_pnl == Decimal("0")
    
    @pytest.mark.asyncio
    async def test_shadow_exit_with_funding_pnl(self, shadow_trader, sample_opportunity):
        """Test exit includes accumulated funding PnL."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        # Record some funding payments
        shadow_trader.record_funding_payment(position.position_id, Decimal("50"))
        shadow_trader.record_funding_payment(position.position_id, Decimal("30"))
        
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        
        assert exit_record.funding_pnl == Decimal("80")
        assert exit_record.total_pnl == Decimal("80")
    
    @pytest.mark.asyncio
    async def test_shadow_exit_with_positive_position_pnl(self, shadow_trader, sample_opportunity):
        """Test exit with positive position PnL."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        # Price goes up on Asgard (long profits)
        # Price goes down on Hyperliquid (short profits)
        shadow_trader.update_prices(position.position_id, Decimal("110"), Decimal("90"))
        
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        
        # Long PnL: (110-100) * (30000/100) = 10 * 300 = 3000
        # Short PnL: (100-90) * (30000/100) = 10 * 300 = 3000
        assert exit_record.position_pnl > Decimal("0")
        assert exit_record.total_pnl > Decimal("0")
    
    @pytest.mark.asyncio
    async def test_shadow_exit_with_negative_position_pnl(self, shadow_trader, sample_opportunity):
        """Test exit with negative position PnL."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        # Price goes down on Asgard (long loses)
        # Price goes up on Hyperliquid (short loses)
        shadow_trader.update_prices(position.position_id, Decimal("95"), Decimal("105"))
        
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        
        assert exit_record.position_pnl < Decimal("0")
    
    @pytest.mark.asyncio
    async def test_shadow_exit_combined_pnl(self, shadow_trader, sample_opportunity):
        """Test exit with both funding and position PnL."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        # Record funding
        shadow_trader.record_funding_payment(position.position_id, Decimal("100"))
        
        # Update prices for positive position PnL
        shadow_trader.update_prices(position.position_id, Decimal("105"), Decimal("95"))
        
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        
        assert exit_record.funding_pnl == Decimal("100")
        assert exit_record.position_pnl > Decimal("0")
        assert exit_record.total_pnl == exit_record.funding_pnl + exit_record.position_pnl


class TestShadowExitReasons:
    """Test different exit reasons."""
    
    @pytest.mark.parametrize("reason", [
        "funding_flip",
        "health_factor",
        "margin_fraction",
        "price_deviation",
        "lst_depeg",
        "manual",
        "chain_outage",
        "stop_loss",
        "target_profit",
    ])
    @pytest.mark.asyncio
    async def test_shadow_exit_various_reasons(self, shadow_trader, sample_opportunity, reason):
        """Test exit with various reasons."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        exit_record = await shadow_trader.shadow_exit(position, reason)
        
        assert exit_record.reason == reason
        assert position.exit_reason == reason


class TestShadowExitTimestamps:
    """Test timestamp handling in shadow exits."""
    
    @pytest.mark.asyncio
    async def test_shadow_exit_timestamp_set(self, shadow_trader, sample_opportunity):
        """Test exit timestamp is set correctly."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        before = datetime.utcnow()
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        after = datetime.utcnow()
        
        assert before <= exit_record.timestamp <= after
        assert before <= position.exit_time <= after
    
    @pytest.mark.asyncio
    async def test_shadow_exit_hold_duration(self, shadow_trader, sample_opportunity):
        """Test hold duration is calculated correctly."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        # Simulate some time passing (not actual sleep)
        position.entry_time = datetime.utcnow() - timedelta(hours=1)
        
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        
        assert exit_record.hold_duration_seconds >= 3600  # At least 1 hour


class TestShadowExitPrices:
    """Test price recording in shadow exits."""
    
    @pytest.mark.asyncio
    async def test_shadow_exit_prices_recorded(self, shadow_trader, sample_opportunity):
        """Test exit prices are recorded."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        # Update prices before exit
        shadow_trader.update_prices(position.position_id, Decimal("105"), Decimal("95"))
        
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        
        assert exit_record.asgard_exit_price == Decimal("105")
        assert exit_record.hyperliquid_exit_price == Decimal("95")
        assert position.exit_asgard_price == Decimal("105")
        assert position.exit_hyperliquid_price == Decimal("95")
    
    @pytest.mark.asyncio
    async def test_shadow_exit_prices_match_current(self, shadow_trader, sample_opportunity):
        """Test exit prices match current position prices."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        shadow_trader.update_prices(position.position_id, Decimal("110"), Decimal("90"))
        
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        
        assert exit_record.asgard_exit_price == position.current_asgard_price
        assert exit_record.hyperliquid_exit_price == position.current_hyperliquid_price


class TestMultipleExits:
    """Test multiple position exits."""
    
    @pytest.mark.asyncio
    async def test_multiple_exits(self, shadow_trader, sample_opportunity):
        """Test exiting multiple positions."""
        pos1 = await shadow_trader.shadow_entry(sample_opportunity)
        pos2 = await shadow_trader.shadow_entry(sample_opportunity)
        pos3 = await shadow_trader.shadow_entry(sample_opportunity)
        
        # Add different funding to each
        shadow_trader.record_funding_payment(pos1.position_id, Decimal("100"))
        shadow_trader.record_funding_payment(pos2.position_id, Decimal("-50"))
        shadow_trader.record_funding_payment(pos3.position_id, Decimal("200"))
        
        # Exit all with different reasons
        await shadow_trader.shadow_exit(pos1, "funding_flip")
        await shadow_trader.shadow_exit(pos2, "manual")
        await shadow_trader.shadow_exit(pos3, "target_profit")
        
        assert len(shadow_trader.get_exit_history()) == 3
        assert len(shadow_trader.get_closed_positions()) == 3
        assert len(shadow_trader.get_open_positions()) == 0
    
    @pytest.mark.asyncio
    async def test_exit_records_independent(self, shadow_trader, sample_opportunity):
        """Test each exit record is independent."""
        pos1 = await shadow_trader.shadow_entry(sample_opportunity)
        pos2 = await shadow_trader.shadow_entry(sample_opportunity)
        
        exit1 = await shadow_trader.shadow_exit(pos1, "reason_a")
        exit2 = await shadow_trader.shadow_exit(pos2, "reason_b")
        
        assert exit1.position_id == pos1.position_id
        assert exit2.position_id == pos2.position_id
        assert exit1.reason == "reason_a"
        assert exit2.reason == "reason_b"


class TestShadowExitWithNegativeFunding:
    """Test exits with negative funding (paying funding)."""
    
    @pytest.mark.asyncio
    async def test_shadow_exit_negative_funding(self, shadow_trader, sample_opportunity):
        """Test exit when funding was negative."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        # Record negative funding (paid funding)
        shadow_trader.record_funding_payment(position.position_id, Decimal("-100"))
        
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        
        assert exit_record.funding_pnl == Decimal("-100")
        assert exit_record.total_pnl < Decimal("0")  # Assuming no position PnL


class TestShadowExitExitPricesInNotes:
    """Test exit record notes."""
    
    @pytest.mark.asyncio
    async def test_shadow_exit_has_notes(self, shadow_trader, sample_opportunity):
        """Test exit record has notes."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        
        assert len(exit_record.notes) > 0
        assert "Shadow exit" in exit_record.notes[0]


class TestRealizedPnL:
    """Test realized PnL calculation."""
    
    @pytest.mark.asyncio
    async def test_realized_pnl_set_on_exit(self, shadow_trader, sample_opportunity):
        """Test realized PnL is set when position is closed."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        shadow_trader.record_funding_payment(position.position_id, Decimal("150"))
        
        await shadow_trader.shadow_exit(position, "manual")
        
        assert position.realized_pnl is not None
        assert position.realized_pnl == Decimal("150")
    
    @pytest.mark.asyncio
    async def test_realized_pnl_matches_exit_total(self, shadow_trader, sample_opportunity):
        """Test realized PnL matches exit record total."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        shadow_trader.record_funding_payment(position.position_id, Decimal("75"))
        shadow_trader.update_prices(position.position_id, Decimal("102"), Decimal("98"))
        
        exit_record = await shadow_trader.shadow_exit(position, "manual")
        
        assert position.realized_pnl == exit_record.total_pnl
