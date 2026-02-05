"""Tests for ShadowTrader PnL calculation functionality."""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta

from src.core.shadow import ShadowTrader, ShadowPnL, ComparisonResult, ShadowPositionStatus
from src.models.opportunity import ArbitrageOpportunity, OpportunityScore
from src.models.common import Asset, Protocol
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


class TestShadowPnLBasic:
    """Test basic PnL calculation."""
    
    @pytest.mark.asyncio
    async def test_empty_pnl(self, shadow_trader):
        """Test PnL with no positions."""
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.total_positions == 0
        assert pnl.open_positions == 0
        assert pnl.closed_positions == 0
        assert pnl.total_realized_pnl == Decimal("0")
        assert pnl.total_unrealized_pnl == Decimal("0")
        assert pnl.total_pnl == Decimal("0")
    
    @pytest.mark.asyncio
    async def test_single_position_pnl(self, shadow_trader, sample_opportunity):
        """Test PnL with single open position."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(position.position_id, Decimal("100"))
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.total_positions == 1
        assert pnl.open_positions == 1
        assert pnl.closed_positions == 0
        assert pnl.total_funding_pnl == Decimal("100")
        assert pnl.total_unrealized_pnl == Decimal("100")
    
    @pytest.mark.asyncio
    async def test_closed_position_realized_pnl(self, shadow_trader, sample_opportunity):
        """Test realized PnL from closed position."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(position.position_id, Decimal("200"))
        await shadow_trader.shadow_exit(position, "manual")
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.closed_positions == 1
        assert pnl.total_realized_pnl == Decimal("200")
        assert pnl.total_unrealized_pnl == Decimal("0")


class TestShadowPnLWinLoss:
    """Test win/loss tracking."""
    
    @pytest.mark.asyncio
    async def test_winning_trade_counted(self, shadow_trader, sample_opportunity):
        """Test winning trades are counted."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(position.position_id, Decimal("100"))
        await shadow_trader.shadow_exit(position, "manual")
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.winning_trades == 1
        assert pnl.losing_trades == 0
    
    @pytest.mark.asyncio
    async def test_losing_trade_counted(self, shadow_trader, sample_opportunity):
        """Test losing trades are counted."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(position.position_id, Decimal("-100"))
        await shadow_trader.shadow_exit(position, "manual")
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.winning_trades == 0
        assert pnl.losing_trades == 1
    
    @pytest.mark.asyncio
    async def test_zero_pnl_not_counted(self, shadow_trader, sample_opportunity):
        """Test zero PnL trades are not counted as win or loss."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        # No funding, no price change = zero PnL
        await shadow_trader.shadow_exit(position, "manual")
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.winning_trades == 0
        assert pnl.losing_trades == 0
    
    @pytest.mark.asyncio
    async def test_mixed_win_loss(self, shadow_trader, sample_opportunity):
        """Test mixed winning and losing trades."""
        # Win
        pos1 = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(pos1.position_id, Decimal("100"))
        await shadow_trader.shadow_exit(pos1, "manual")
        
        # Loss
        pos2 = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(pos2.position_id, Decimal("-50"))
        await shadow_trader.shadow_exit(pos2, "manual")
        
        # Win
        pos3 = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(pos3.position_id, Decimal("75"))
        await shadow_trader.shadow_exit(pos3, "manual")
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.winning_trades == 2
        assert pnl.losing_trades == 1


class TestShadowPnLWinRate:
    """Test win rate calculation."""
    
    @pytest.mark.asyncio
    async def test_win_rate_calculation(self, shadow_trader, sample_opportunity):
        """Test win rate is calculated correctly."""
        # 2 wins, 1 loss
        for funding in [Decimal("100"), Decimal("-50"), Decimal("75")]:
            pos = await shadow_trader.shadow_entry(sample_opportunity)
            shadow_trader.record_funding_payment(pos.position_id, funding)
            await shadow_trader.shadow_exit(pos, "manual")
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.win_rate == Decimal("0.6666666666666666666666666667")  # 2/3
    
    @pytest.mark.asyncio
    async def test_win_rate_100_percent(self, shadow_trader, sample_opportunity):
        """Test 100% win rate."""
        for _ in range(3):
            pos = await shadow_trader.shadow_entry(sample_opportunity)
            shadow_trader.record_funding_payment(pos.position_id, Decimal("100"))
            await shadow_trader.shadow_exit(pos, "manual")
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.win_rate == Decimal("1")
    
    @pytest.mark.asyncio
    async def test_win_rate_0_percent(self, shadow_trader, sample_opportunity):
        """Test 0% win rate."""
        for _ in range(3):
            pos = await shadow_trader.shadow_entry(sample_opportunity)
            shadow_trader.record_funding_payment(pos.position_id, Decimal("-100"))
            await shadow_trader.shadow_exit(pos, "manual")
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.win_rate == Decimal("0")
    
    @pytest.mark.asyncio
    async def test_win_rate_no_trades(self, shadow_trader):
        """Test win rate with no trades."""
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.win_rate == Decimal("0")


class TestShadowPnLAverage:
    """Test average PnL calculations."""
    
    @pytest.mark.asyncio
    async def test_average_pnl_per_trade(self, shadow_trader, sample_opportunity):
        """Test average PnL per trade."""
        # Trades: +100, +200, -50 = +250 total, avg = 83.33
        for funding in [Decimal("100"), Decimal("200"), Decimal("-50")]:
            pos = await shadow_trader.shadow_entry(sample_opportunity)
            shadow_trader.record_funding_payment(pos.position_id, funding)
            await shadow_trader.shadow_exit(pos, "manual")
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.average_pnl_per_trade == Decimal("250") / Decimal("3")
    
    @pytest.mark.asyncio
    async def test_average_pnl_no_trades(self, shadow_trader):
        """Test average PnL with no trades."""
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.average_pnl_per_trade == Decimal("0")


class TestShadowPnLPositionPnl:
    """Test position PnL component."""
    
    @pytest.mark.asyncio
    async def test_position_pnl_calculated(self, shadow_trader, sample_opportunity):
        """Test position PnL is tracked."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        # Update prices to create position PnL
        shadow_trader.update_prices(position.position_id, Decimal("102"), Decimal("98"))
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.total_position_pnl != Decimal("0")
    
    @pytest.mark.asyncio
    async def test_position_pnl_and_funding_combined(self, shadow_trader, sample_opportunity):
        """Test position and funding PnL combined."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        shadow_trader.record_funding_payment(position.position_id, Decimal("100"))
        shadow_trader.update_prices(position.position_id, Decimal("105"), Decimal("95"))
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.total_funding_pnl == Decimal("100")
        assert pnl.total_position_pnl > Decimal("0")


class TestShadowPnLToDict:
    """Test PnL dictionary conversion."""
    
    @pytest.mark.asyncio
    async def test_pnl_to_dict(self, shadow_trader, sample_opportunity):
        """Test PnL converts to dictionary."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(position.position_id, Decimal("100"))
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        d = pnl.to_dict()
        
        assert isinstance(d, dict)
        assert d["total_positions"] == 1
        assert d["total_funding_pnl"] == 100.0
        assert d["winning_trades"] == 0  # Position still open
        assert d["open_positions"] == 1
    
    @pytest.mark.asyncio
    async def test_pnl_dict_float_conversion(self, shadow_trader, sample_opportunity):
        """Test PnL values convert to float in dict."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(position.position_id, Decimal("123.45"))
        await shadow_trader.shadow_exit(position, "manual")
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        d = pnl.to_dict()
        
        assert isinstance(d["total_realized_pnl"], float)
        assert isinstance(d["win_rate"], float)


class TestShadowPnLMixedPositions:
    """Test PnL with mix of open and closed positions."""
    
    @pytest.mark.asyncio
    async def test_mixed_open_closed_positions(self, shadow_trader, sample_opportunity):
        """Test PnL with both open and closed positions."""
        # Closed position
        pos1 = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(pos1.position_id, Decimal("100"))
        await shadow_trader.shadow_exit(pos1, "manual")
        
        # Open position
        pos2 = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(pos2.position_id, Decimal("50"))
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.total_positions == 2
        assert pnl.closed_positions == 1
        assert pnl.open_positions == 1
        assert pnl.total_realized_pnl == Decimal("100")
        assert pnl.total_unrealized_pnl == Decimal("50")
        assert pnl.total_pnl == Decimal("150")


class TestComparisonToMarket:
    """Test market comparison functionality."""
    
    @pytest.mark.asyncio
    async def test_comparison_basic(self, shadow_trader, sample_opportunity):
        """Test basic market comparison."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(position.position_id, Decimal("500"))
        await shadow_trader.shadow_exit(position, "manual")
        
        result = await shadow_trader.compare_to_market(
            benchmark_price_start=Decimal("100"),
            benchmark_price_end=Decimal("110"),
            duration_days=Decimal("30"),
        )
        
        assert isinstance(result, ComparisonResult)
        assert result.shadow_total_pnl > Decimal("0")
    
    @pytest.mark.asyncio
    async def test_comparison_outperformance(self, shadow_trader, sample_opportunity):
        """Test outperformance calculation."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(position.position_id, Decimal("1000"))
        await shadow_trader.shadow_exit(position, "manual")
        
        result = await shadow_trader.compare_to_market(
            benchmark_price_start=Decimal("100"),
            benchmark_price_end=Decimal("105"),  # 5% market return
            duration_days=Decimal("30"),
        )
        
        # Shadow made $1000 on $10000 = 10% return
        # Market made 5% return
        # Shadow outperformed
        assert result.outperformance > Decimal("0")
    
    @pytest.mark.asyncio
    async def test_comparison_underperformance(self, shadow_trader, sample_opportunity):
        """Test underperformance when market does better."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(position.position_id, Decimal("100"))  # Small profit
        await shadow_trader.shadow_exit(position, "manual")
        
        result = await shadow_trader.compare_to_market(
            benchmark_price_start=Decimal("100"),
            benchmark_price_end=Decimal("120"),  # 20% market return
            duration_days=Decimal("30"),
        )
        
        assert result.outperformance < Decimal("0")
    
    @pytest.mark.asyncio
    async def test_comparison_no_positions(self, shadow_trader):
        """Test comparison with no positions."""
        result = await shadow_trader.compare_to_market(
            benchmark_price_start=Decimal("100"),
            benchmark_price_end=Decimal("110"),
            duration_days=Decimal("30"),
        )
        
        assert result.shadow_total_pnl == Decimal("0")
        assert result.market_total_return == Decimal("0.1")  # 10%
    
    @pytest.mark.asyncio
    async def test_comparison_to_dict(self, shadow_trader, sample_opportunity):
        """Test comparison result to dictionary."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        shadow_trader.record_funding_payment(position.position_id, Decimal("500"))
        await shadow_trader.shadow_exit(position, "manual")
        
        result = await shadow_trader.compare_to_market(
            benchmark_price_start=Decimal("100"),
            benchmark_price_end=Decimal("110"),
            duration_days=Decimal("30"),
        )
        
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "shadow_total_pnl" in d
        assert "market_total_return" in d
        assert "outperformance" in d


class TestShadowPnLFundingPaymentsTracking:
    """Test funding payments tracking."""
    
    @pytest.mark.asyncio
    async def test_multiple_funding_payments(self, shadow_trader, sample_opportunity):
        """Test multiple funding payments are summed."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        payments = [Decimal("10"), Decimal("15"), Decimal("20"), Decimal("-5")]
        for payment in payments:
            shadow_trader.record_funding_payment(position.position_id, payment)
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.total_funding_pnl == Decimal("40")
    
    @pytest.mark.asyncio
    async def test_funding_payments_multiple_positions(self, shadow_trader, sample_opportunity):
        """Test funding across multiple positions."""
        pos1 = await shadow_trader.shadow_entry(sample_opportunity)
        pos2 = await shadow_trader.shadow_entry(sample_opportunity)
        
        shadow_trader.record_funding_payment(pos1.position_id, Decimal("100"))
        shadow_trader.record_funding_payment(pos2.position_id, Decimal("200"))
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        
        assert pnl.total_funding_pnl == Decimal("300")


class TestShadowPnLReset:
    """Test trader reset functionality."""
    
    @pytest.mark.asyncio
    async def test_reset_clears_positions(self, shadow_trader, sample_opportunity):
        """Test reset clears all positions."""
        await shadow_trader.shadow_entry(sample_opportunity)
        await shadow_trader.shadow_entry(sample_opportunity)
        
        shadow_trader.reset()
        
        pnl = await shadow_trader.calculate_shadow_pnl()
        assert pnl.total_positions == 0
    
    @pytest.mark.asyncio
    async def test_reset_clears_entries(self, shadow_trader, sample_opportunity):
        """Test reset clears entry history."""
        await shadow_trader.shadow_entry(sample_opportunity)
        
        shadow_trader.reset()
        
        assert len(shadow_trader.get_entry_history()) == 0
    
    @pytest.mark.asyncio
    async def test_reset_clears_exits(self, shadow_trader, sample_opportunity):
        """Test reset clears exit history."""
        pos = await shadow_trader.shadow_entry(sample_opportunity)
        await shadow_trader.shadow_exit(pos, "manual")
        
        shadow_trader.reset()
        
        assert len(shadow_trader.get_exit_history()) == 0
    
    def test_reset_clears_counter(self, shadow_trader):
        """Test reset clears position counter."""
        # Generate some IDs
        shadow_trader._generate_position_id()
        shadow_trader._generate_position_id()
        
        shadow_trader.reset()
        
        assert shadow_trader._position_counter == 0
