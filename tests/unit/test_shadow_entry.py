"""Tests for ShadowTrader entry logging functionality."""
import pytest
from decimal import Decimal
from datetime import datetime

from src.core.shadow import ShadowTrader, ShadowPosition, ShadowPositionStatus
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
def lst_opportunity():
    """Create an LST arbitrage opportunity."""
    return ArbitrageOpportunity(
        id="opp_lst_67890",
        asset=Asset.JITOSOL,
        selected_protocol=Protocol.MARGINFI,
        asgard_rates=AsgardRates(
            protocol_id=0,
            token_a_mint="jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v",
            token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            token_a_lending_apy=Decimal("0.13"),  # 5% base + 8% staking
            token_b_borrowing_apy=Decimal("0.08"),
            token_b_max_borrow_capacity=Decimal("1000000"),
        ),
        hyperliquid_coin="SOL",
        current_funding=FundingRate(
            timestamp=datetime.utcnow(),
            coin="SOL",
            rate_8hr=Decimal("-0.0004"),
        ),
        predicted_funding=FundingRate(
            timestamp=datetime.utcnow(),
            coin="SOL",
            rate_8hr=Decimal("-0.00035"),
        ),
        funding_volatility=Decimal("0.15"),
        leverage=Decimal("3"),
        deployed_capital_usd=Decimal("20000"),
        position_size_usd=Decimal("60000"),
        score=OpportunityScore(
            funding_apy=Decimal("0.30"),
            net_carry_apy=Decimal("0.08"),
            lst_staking_apy=Decimal("0.08"),
            estimated_gas_cost_apy=Decimal("0.001"),
            estimated_slippage_apy=Decimal("0.005"),
        ),
        price_deviation=Decimal("0.002"),
        preflight_checks_passed=True,
    )


class TestShadowTraderInitialization:
    """Test ShadowTrader initialization."""
    
    def test_initialization(self):
        """Test ShadowTrader initializes correctly."""
        trader = ShadowTrader()
        
        assert trader._positions == {}
        assert trader._entries == []
        assert trader._exits == []
        assert trader._position_counter == 0
    
    def test_generate_position_id(self):
        """Test position ID generation."""
        trader = ShadowTrader()
        
        id1 = trader._generate_position_id()
        id2 = trader._generate_position_id()
        
        assert id1.startswith("shadow_")
        assert id2.startswith("shadow_")
        assert id1 != id2
        assert trader._position_counter == 2


class TestShadowEntry:
    """Test shadow entry logging functionality."""
    
    @pytest.mark.asyncio
    async def test_shadow_entry_basic(self, shadow_trader, sample_opportunity):
        """Test basic shadow entry creates position."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        assert position is not None
        assert position.position_id.startswith("shadow_")
        assert position.opportunity_id == sample_opportunity.id
        assert position.asset == Asset.SOL
        assert position.protocol == Protocol.KAMINO
        assert position.status == ShadowPositionStatus.OPEN
        assert position.is_open is True
        assert position.is_closed is False
    
    @pytest.mark.asyncio
    async def test_shadow_entry_position_sizing(self, shadow_trader, sample_opportunity):
        """Test shadow entry records correct position sizing."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        assert position.deployed_capital_usd == Decimal("10000")
        assert position.per_leg_deployment_usd == Decimal("5000")
        assert position.position_size_usd == Decimal("30000")
        assert position.leverage == Decimal("3")
    
    @pytest.mark.asyncio
    async def test_shadow_entry_expected_yields(self, shadow_trader, sample_opportunity):
        """Test shadow entry records expected yields."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        assert position.expected_funding_apy == Decimal("0.25")
        assert position.expected_net_carry_apy == Decimal("0.02")
        assert position.expected_total_apy == Decimal("0.264")  # 0.25 + 0.02 - 0.001 - 0.005
    
    @pytest.mark.asyncio
    async def test_shadow_entry_stores_position(self, shadow_trader, sample_opportunity):
        """Test shadow entry stores position in trader."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        stored_position = shadow_trader.get_position(position.position_id)
        assert stored_position is not None
        assert stored_position.position_id == position.position_id
    
    @pytest.mark.asyncio
    async def test_shadow_entry_creates_entry_record(self, shadow_trader, sample_opportunity):
        """Test shadow entry creates entry record."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        entries = shadow_trader.get_entry_history()
        assert len(entries) == 1
        
        entry = entries[0]
        assert entry.opportunity_id == sample_opportunity.id
        assert entry.asset == "SOL"
        assert entry.protocol == "KAMINO"
        assert entry.leverage == Decimal("3")
        assert entry.deployed_capital_usd == Decimal("10000")
        assert entry.position_size_usd == Decimal("30000")
    
    @pytest.mark.asyncio
    async def test_shadow_entry_multiple_positions(self, shadow_trader, sample_opportunity):
        """Test creating multiple shadow positions."""
        pos1 = await shadow_trader.shadow_entry(sample_opportunity)
        pos2 = await shadow_trader.shadow_entry(sample_opportunity)
        
        assert pos1.position_id != pos2.position_id
        assert len(shadow_trader._positions) == 2
        assert len(shadow_trader.get_entry_history()) == 2
    
    @pytest.mark.asyncio
    async def test_shadow_entry_with_lst(self, shadow_trader, lst_opportunity):
        """Test shadow entry with LST asset."""
        position = await shadow_trader.shadow_entry(lst_opportunity)
        
        assert position.asset == Asset.JITOSOL
        assert position.protocol == Protocol.MARGINFI
        assert position.expected_total_apy > lst_opportunity.score.total_net_apy * Decimal("0.9")
    
    @pytest.mark.asyncio
    async def test_shadow_entry_entry_record_link(self, shadow_trader, sample_opportunity):
        """Test position links to entry record."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        assert position.entry_record is not None
        assert position.entry_record.opportunity_id == sample_opportunity.id
        assert position.entry_record.timestamp == position.entry_time


class TestShadowEntryWithDifferentAssets:
    """Test shadow entry with different asset types."""
    
    @pytest.mark.asyncio
    async def test_shadow_entry_jitosol(self, shadow_trader):
        """Test entry with jitoSOL."""
        opp = ArbitrageOpportunity(
            id="opp_jitosol",
            asset=Asset.JITOSOL,
            selected_protocol=Protocol.KAMINO,
            asgard_rates=AsgardRates(
                protocol_id=1,
                token_a_mint="jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v",
                token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                token_a_lending_apy=Decimal("0.13"),
                token_b_borrowing_apy=Decimal("0.08"),
                token_b_max_borrow_capacity=Decimal("1000000"),
            ),
            hyperliquid_coin="SOL",
            current_funding=FundingRate(
                timestamp=datetime.utcnow(),
                coin="SOL", 
                rate_8hr=Decimal("-0.0003")
            ),
            funding_volatility=Decimal("0.1"),
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("5000"),
            position_size_usd=Decimal("15000"),
            score=OpportunityScore(funding_apy=Decimal("0.25"), net_carry_apy=Decimal("0.08")),
            price_deviation=Decimal("0.001"),
        )
        
        position = await shadow_trader.shadow_entry(opp)
        assert position.asset == Asset.JITOSOL
    
    @pytest.mark.asyncio
    async def test_shadow_entry_jupsol(self, shadow_trader):
        """Test entry with jupSOL."""
        opp = ArbitrageOpportunity(
            id="opp_jupsol",
            asset=Asset.JUPSOL,
            selected_protocol=Protocol.SOLEND,
            asgard_rates=AsgardRates(
                protocol_id=2,
                token_a_mint="jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v",
                token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                token_a_lending_apy=Decimal("0.12"),
                token_b_borrowing_apy=Decimal("0.08"),
                token_b_max_borrow_capacity=Decimal("1000000"),
            ),
            hyperliquid_coin="SOL",
            current_funding=FundingRate(
                timestamp=datetime.utcnow(),
                coin="SOL", 
                rate_8hr=Decimal("-0.0003")
            ),
            funding_volatility=Decimal("0.1"),
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("5000"),
            position_size_usd=Decimal("15000"),
            score=OpportunityScore(funding_apy=Decimal("0.25"), net_carry_apy=Decimal("0.07")),
            price_deviation=Decimal("0.001"),
        )
        
        position = await shadow_trader.shadow_entry(opp)
        assert position.asset == Asset.JUPSOL
    
    @pytest.mark.asyncio
    async def test_shadow_entry_inf(self, shadow_trader):
        """Test entry with INF."""
        opp = ArbitrageOpportunity(
            id="opp_inf",
            asset=Asset.INF,
            selected_protocol=Protocol.DRIFT,
            asgard_rates=AsgardRates(
                protocol_id=3,
                token_a_mint="5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X6TxNxsi",
                token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                token_a_lending_apy=Decimal("0.11"),
                token_b_borrowing_apy=Decimal("0.08"),
                token_b_max_borrow_capacity=Decimal("1000000"),
            ),
            hyperliquid_coin="SOL",
            current_funding=FundingRate(
                timestamp=datetime.utcnow(),
                coin="SOL", 
                rate_8hr=Decimal("-0.0003")
            ),
            funding_volatility=Decimal("0.1"),
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("5000"),
            position_size_usd=Decimal("15000"),
            score=OpportunityScore(funding_apy=Decimal("0.25"), net_carry_apy=Decimal("0.06")),
            price_deviation=Decimal("0.001"),
        )
        
        position = await shadow_trader.shadow_entry(opp)
        assert position.asset == Asset.INF


class TestShadowEntryWithDifferentProtocols:
    """Test shadow entry with different protocols."""
    
    @pytest.mark.parametrize("protocol,protocol_id,protocol_name", [
        (Protocol.MARGINFI, 0, "MARGINFI"),
        (Protocol.KAMINO, 1, "KAMINO"),
        (Protocol.SOLEND, 2, "SOLEND"),
        (Protocol.DRIFT, 3, "DRIFT"),
    ])
    @pytest.mark.asyncio
    async def test_shadow_entry_protocol(self, shadow_trader, sample_opportunity, 
                                          protocol, protocol_id, protocol_name):
        """Test entry with each protocol."""
        sample_opportunity.selected_protocol = protocol
        sample_opportunity.asgard_rates.protocol_id = protocol_id
        
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        assert position.protocol == protocol
        
        entry = shadow_trader.get_entry_history()[0]
        assert entry.protocol == protocol_name


class TestShadowEntryWithDifferentLeverage:
    """Test shadow entry with different leverage levels."""
    
    @pytest.mark.parametrize("leverage", [Decimal("2"), Decimal("3"), Decimal("4")])
    @pytest.mark.asyncio
    async def test_shadow_entry_leverage(self, shadow_trader, sample_opportunity, leverage):
        """Test entry with different leverage levels."""
        sample_opportunity.leverage = leverage
        sample_opportunity.position_size_usd = sample_opportunity.deployed_capital_usd * leverage
        
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        assert position.leverage == leverage
        assert position.position_size_usd == sample_opportunity.deployed_capital_usd * leverage


class TestShadowEntryTimestamps:
    """Test timestamp handling in shadow entries."""
    
    @pytest.mark.asyncio
    async def test_shadow_entry_timestamp_set(self, shadow_trader, sample_opportunity):
        """Test entry timestamp is set correctly."""
        before = datetime.utcnow()
        position = await shadow_trader.shadow_entry(sample_opportunity)
        after = datetime.utcnow()
        
        assert before <= position.entry_time <= after
    
    @pytest.mark.asyncio
    async def test_shadow_entry_record_timestamp(self, shadow_trader, sample_opportunity):
        """Test entry record has same timestamp as position."""
        position = await shadow_trader.shadow_entry(sample_opportunity)
        
        assert position.entry_record is not None
        assert position.entry_record.timestamp == position.entry_time
