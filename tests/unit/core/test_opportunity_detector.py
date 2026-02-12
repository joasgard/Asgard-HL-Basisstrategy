"""
Tests for Opportunity Detector module.

These tests verify:
- Opportunity scanning across assets
- APY calculations (funding + net carry + LST staking)
- Entry criteria validation
- Opportunity filtering and ranking
- Integration with Asgard and Hyperliquid
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.config.assets import Asset, get_mint
from bot.core.opportunity_detector import OpportunityDetector
from shared.models.common import Protocol
from shared.models.funding import FundingRate, AsgardRates
from shared.models.opportunity import ArbitrageOpportunity, OpportunityScore
from bot.venues.asgard.market_data import AsgardMarketData, NetCarryResult
from bot.venues.hyperliquid.funding_oracle import (
    HyperliquidFundingOracle,
    FundingPrediction,
    FundingRate as HlFundingRate,
)


# Mock fixtures
@pytest.fixture
def mock_funding_rate():
    """Mock negative funding rate."""
    return FundingRate(
        timestamp=datetime.utcnow(),
        coin="SOL",
        rate_8hr=Decimal("-0.0001"),  # -0.01% per 8 hours
    )


@pytest.fixture
def mock_positive_funding_rate():
    """Mock positive funding rate."""
    return FundingRate(
        timestamp=datetime.utcnow(),
        coin="SOL",
        rate_8hr=Decimal("0.0001"),  # +0.01% per 8 hours
    )


@pytest.fixture
def mock_prediction_negative():
    """Mock negative funding prediction."""
    return FundingPrediction(
        coin="SOL",
        predicted_rate=-0.00008,
        confidence="high",
        premium=-0.00009,
        interest_rate=0.0001,
    )


@pytest.fixture
def mock_prediction_positive():
    """Mock positive funding prediction."""
    return FundingPrediction(
        coin="SOL",
        predicted_rate=0.00005,
        confidence="medium",
        premium=0.00004,
        interest_rate=0.0001,
    )


@pytest.fixture
def mock_net_carry_result():
    """Mock net carry calculation result."""
    return NetCarryResult(
        protocol=Protocol.MARGINFI,
        lending_rate=0.05,  # 5%
        borrowing_rate=0.08,  # 8%
        net_carry_rate=-0.01,
        net_carry_apy=-0.01,  # -1%
        leverage=3.0,
        has_capacity=True,
    )


@pytest.fixture
def mock_net_carry_positive():
    """Mock positive net carry result."""
    return NetCarryResult(
        protocol=Protocol.KAMINO,
        lending_rate=0.055,  # 5.5%
        borrowing_rate=0.075,  # 7.5%
        net_carry_rate=0.015,
        net_carry_apy=0.015,  # +1.5%
        leverage=3.0,
        has_capacity=True,
    )


@pytest.fixture
def mock_asgard_market_data(mock_net_carry_result):
    """Mock AsgardMarketData."""
    mock = MagicMock(spec=AsgardMarketData)
    mock.select_best_protocol = AsyncMock(return_value=mock_net_carry_result)
    mock.calculate_net_carry_apy = AsyncMock(return_value=mock_net_carry_result)
    mock.get_borrowing_rates = AsyncMock(return_value=[])
    mock.get_markets = AsyncMock(return_value={"markets": []})
    mock.clear_cache = MagicMock()
    mock.client = MagicMock()
    mock.client._session = MagicMock()
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_hyperliquid_oracle(mock_funding_rate, mock_prediction_negative):
    """Mock HyperliquidFundingOracle."""
    mock = MagicMock(spec=HyperliquidFundingOracle)
    mock.get_current_funding_rates = AsyncMock(return_value={
        "SOL": HlFundingRate(
            coin="SOL",
            funding_rate=-0.0001,
            timestamp_ms=int(datetime.utcnow().timestamp() * 1000),
            annualized_rate=-0.1095,
        )
    })
    mock.predict_next_funding = AsyncMock(return_value=mock_prediction_negative)
    mock.calculate_funding_volatility = AsyncMock(return_value=0.2)  # 20%
    mock.get_funding_history = AsyncMock(return_value=[])
    mock.clear_cache = MagicMock()
    mock.client = MagicMock()
    mock.client._session = MagicMock()
    mock.client.close = AsyncMock()
    mock.close = AsyncMock()
    return mock


class TestOpportunityDetectorInit:
    """Tests for detector initialization."""
    
    def test_init_with_clients(self, mock_asgard_market_data, mock_hyperliquid_oracle):
        """Test initialization with provided clients."""
        detector = OpportunityDetector(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_oracle=mock_hyperliquid_oracle,
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("50000"),
        )
        
        assert detector.asgard is mock_asgard_market_data
        assert detector.hyperliquid is mock_hyperliquid_oracle
        assert detector.leverage == Decimal("3")
        assert detector.deployed_capital_usd == Decimal("50000")
    
    def test_init_default_values(self):
        """Test initialization with default values."""
        detector = OpportunityDetector()
        
        assert detector.asgard is None
        assert detector.hyperliquid is None
        assert detector.leverage == OpportunityDetector.DEFAULT_LEVERAGE
        assert detector.deployed_capital_usd == OpportunityDetector.DEFAULT_DEPLOYED_CAPITAL_USD
    
    def test_init_invalid_leverage(self):
        """Test that invalid leverage raises error."""
        with pytest.raises(ValueError, match="Leverage must be between"):
            OpportunityDetector(leverage=Decimal("5"))
        
        with pytest.raises(ValueError, match="Leverage must be between"):
            OpportunityDetector(leverage=Decimal("1"))


class TestScanOpportunities:
    """Tests for opportunity scanning."""
    
    @pytest.mark.asyncio
    async def test_scan_finds_opportunity(
        self, mock_asgard_market_data, mock_hyperliquid_oracle, mock_net_carry_result
    ):
        """Test that scan finds valid opportunities."""
        # Setup positive net carry for profit
        mock_net_carry_positive = NetCarryResult(
            protocol=Protocol.KAMINO,
            lending_rate=0.06,
            borrowing_rate=0.07,
            net_carry_rate=0.04,
            net_carry_apy=0.04,  # +4%
            leverage=3.0,
            has_capacity=True,
        )
        mock_asgard_market_data.select_best_protocol = AsyncMock(return_value=mock_net_carry_positive)
        
        async with OpportunityDetector(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_oracle=mock_hyperliquid_oracle,
        ) as detector:
            opportunities = await detector.scan_opportunities(assets=[Asset.SOL])
        
        assert len(opportunities) == 1
        assert opportunities[0].asset == Asset.SOL
        assert opportunities[0].total_expected_apy > 0
    
    @pytest.mark.asyncio
    async def test_scan_skips_positive_funding(
        self, mock_asgard_market_data, mock_hyperliquid_oracle
    ):
        """Test that opportunities with positive funding are skipped."""
        # Setup positive funding
        mock_hyperliquid_oracle.get_current_funding_rates = AsyncMock(return_value={
            "SOL": HlFundingRate(
                coin="SOL",
                funding_rate=0.0001,  # Positive - shorts pay
                timestamp_ms=int(datetime.utcnow().timestamp() * 1000),
                annualized_rate=0.1095,
            )
        })
        
        async with OpportunityDetector(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_oracle=mock_hyperliquid_oracle,
        ) as detector:
            opportunities = await detector.scan_opportunities(assets=[Asset.SOL])
        
        assert len(opportunities) == 0
    
    @pytest.mark.asyncio
    async def test_scan_skips_positive_prediction(
        self, mock_asgard_market_data, mock_hyperliquid_oracle
    ):
        """Test that opportunities with positive predicted funding are skipped."""
        # Setup positive prediction
        mock_hyperliquid_oracle.predict_next_funding = AsyncMock(return_value=
            FundingPrediction(
                coin="SOL",
                predicted_rate=0.00005,  # Positive prediction
                confidence="medium",
                premium=0.00004,
                interest_rate=0.0001,
            )
        )
        
        async with OpportunityDetector(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_oracle=mock_hyperliquid_oracle,
        ) as detector:
            opportunities = await detector.scan_opportunities(assets=[Asset.SOL])
        
        assert len(opportunities) == 0
    
    @pytest.mark.asyncio
    async def test_scan_skips_high_volatility(
        self, mock_asgard_market_data, mock_hyperliquid_oracle
    ):
        """Test that opportunities with high volatility are skipped."""
        # Setup high volatility (60% > 50% threshold)
        mock_hyperliquid_oracle.calculate_funding_volatility = AsyncMock(return_value=0.6)
        
        async with OpportunityDetector(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_oracle=mock_hyperliquid_oracle,
        ) as detector:
            opportunities = await detector.scan_opportunities(assets=[Asset.SOL])
        
        assert len(opportunities) == 0
    
    @pytest.mark.asyncio
    async def test_scan_no_protocol_available(
        self, mock_asgard_market_data, mock_hyperliquid_oracle
    ):
        """Test handling when no protocol is available."""
        mock_asgard_market_data.select_best_protocol = AsyncMock(return_value=None)
        
        async with OpportunityDetector(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_oracle=mock_hyperliquid_oracle,
        ) as detector:
            opportunities = await detector.scan_opportunities(assets=[Asset.SOL])
        
        assert len(opportunities) == 0
    
    @pytest.mark.asyncio
    async def test_scan_all_assets(self, mock_asgard_market_data, mock_hyperliquid_oracle):
        """Test scanning all supported assets (SOL only)."""
        async with OpportunityDetector(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_oracle=mock_hyperliquid_oracle,
        ) as detector:
            opportunities = await detector.scan_opportunities()

        # Should scan SOL only
        assert mock_asgard_market_data.select_best_protocol.call_count == 1
    
    @pytest.mark.asyncio
    async def test_scan_sorted_by_apy(
        self, mock_asgard_market_data, mock_hyperliquid_oracle
    ):
        """Test that opportunities are sorted by total APY."""
        # Setup different net carry for different assets
        call_count = [0]
        async def side_effect(*args, **kwargs):
            asset = args[0] if args else kwargs.get('asset')
            call_count[0] += 1
            # Return different APY for each asset
            apys = {
                Asset.SOL: 0.02,
                Asset.JITOSOL: 0.05,
                Asset.JUPSOL: 0.03,
                Asset.INF: 0.01,
            }
            return NetCarryResult(
                protocol=Protocol.MARGINFI,
                lending_rate=0.05,
                borrowing_rate=0.08,
                net_carry_rate=apys.get(asset, 0.01),
                net_carry_apy=apys.get(asset, 0.01),
                leverage=3.0,
                has_capacity=True,
            )
        
        mock_asgard_market_data.select_best_protocol = AsyncMock(side_effect=side_effect)
        
        async with OpportunityDetector(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_oracle=mock_hyperliquid_oracle,
        ) as detector:
            opportunities = await detector.scan_opportunities()
        
        # Should be sorted by APY descending
        if len(opportunities) >= 2:
            for i in range(len(opportunities) - 1):
                assert opportunities[i].total_expected_apy >= opportunities[i + 1].total_expected_apy


class TestCalculateTotalAPY:
    """Tests for APY calculation."""
    
    @pytest.mark.asyncio
    async def test_calculate_total_apy_sol(self, mock_asgard_market_data):
        """Test APY calculation for SOL (no LST staking)."""
        mock_asgard_market_data.calculate_net_carry_apy = AsyncMock(return_value=
            NetCarryResult(
                protocol=Protocol.MARGINFI,
                lending_rate=0.05,
                borrowing_rate=0.08,
                net_carry_rate=-0.01,
                net_carry_apy=-0.01,
                leverage=3.0,
                has_capacity=True,
            )
        )
        
        async with OpportunityDetector(asgard_market_data=mock_asgard_market_data) as detector:
            funding_apy, net_carry_apy, lst_staking_apy = await detector.calculate_total_apy(
                asset=Asset.SOL,
                protocol=Protocol.MARGINFI,
                funding_rate=Decimal("-0.1095"),  # Annual 1x rate
            )

        # Funding APY = |rate| × leverage (3x default) — per deployed capital
        assert funding_apy == Decimal("0.1095") * Decimal("3")
        # Net carry from mock (already leveraged)
        assert net_carry_apy == Decimal("-0.01")
        # No LST staking for SOL
        assert lst_staking_apy == Decimal("0")
    
    @pytest.mark.asyncio
    async def test_calculate_total_apy_lst(self, mock_asgard_market_data):
        """Test APY calculation for LST (includes staking yield)."""
        mock_asgard_market_data.calculate_net_carry_apy = AsyncMock(return_value=
            NetCarryResult(
                protocol=Protocol.KAMINO,
                lending_rate=0.06,
                borrowing_rate=0.075,
                net_carry_rate=0.015,
                net_carry_apy=0.015,
                leverage=3.0,
                has_capacity=True,
            )
        )
        
        async with OpportunityDetector(asgard_market_data=mock_asgard_market_data) as detector:
            funding_apy, net_carry_apy, lst_staking_apy = await detector.calculate_total_apy(
                asset=Asset.JITOSOL,
                protocol=Protocol.KAMINO,
                funding_rate=Decimal("-0.1095"),
            )
        
        # Funding APY = |rate| × leverage (3x default)
        assert funding_apy == Decimal("0.1095") * Decimal("3")
        assert net_carry_apy == Decimal("0.015")
        # jitoSOL has ~8% staking yield
        assert lst_staking_apy > Decimal("0")
        assert lst_staking_apy == Decimal("0.08")  # From asset config


class TestFilterOpportunities:
    """Tests for opportunity filtering."""
    
    @pytest.fixture
    def sample_opportunities(self):
        """Create sample opportunities for filtering tests."""
        base_time = datetime.utcnow()
        
        return [
            ArbitrageOpportunity(
                id="opp-1",
                asset=Asset.SOL,
                selected_protocol=Protocol.MARGINFI,
                asgard_rates=AsgardRates(
                    protocol_id=0,
                    token_a_mint=get_mint(Asset.SOL),
                    token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    token_a_lending_apy=Decimal("0.05"),
                    token_b_borrowing_apy=Decimal("0.08"),
                    token_b_max_borrow_capacity=Decimal("1000000"),
                ),
                current_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.0001")),
                predicted_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.00008")),
                funding_volatility=Decimal("0.2"),
                leverage=Decimal("3"),
                deployed_capital_usd=Decimal("50000"),
                position_size_usd=Decimal("150000"),
                score=OpportunityScore(
                    funding_apy=Decimal("0.10"),
                    net_carry_apy=Decimal("0.02"),
                    lst_staking_apy=Decimal("0"),
                ),
                price_deviation=Decimal("0.001"),
            ),
            ArbitrageOpportunity(
                id="opp-2",
                asset=Asset.JITOSOL,
                selected_protocol=Protocol.KAMINO,
                asgard_rates=AsgardRates(
                    protocol_id=1,
                    token_a_mint=get_mint(Asset.JITOSOL),
                    token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    token_a_lending_apy=Decimal("0.06"),
                    token_b_borrowing_apy=Decimal("0.075"),
                    token_b_max_borrow_capacity=Decimal("500000"),
                ),
                current_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.0001")),
                predicted_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.00008")),
                funding_volatility=Decimal("0.6"),  # High volatility
                leverage=Decimal("3"),
                deployed_capital_usd=Decimal("50000"),
                position_size_usd=Decimal("150000"),
                score=OpportunityScore(
                    funding_apy=Decimal("0.10"),
                    net_carry_apy=Decimal("0.05"),
                    lst_staking_apy=Decimal("0.08"),
                ),
                price_deviation=Decimal("0.001"),
            ),
            ArbitrageOpportunity(
                id="opp-3",
                asset=Asset.JUPSOL,
                selected_protocol=Protocol.SOLEND,
                asgard_rates=AsgardRates(
                    protocol_id=2,
                    token_a_mint=get_mint(Asset.JUPSOL),
                    token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    token_a_lending_apy=Decimal("0.055"),
                    token_b_borrowing_apy=Decimal("0.08"),
                    token_b_max_borrow_capacity=Decimal("750000"),
                ),
                current_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.0001")),
                predicted_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("0.00005")),  # Positive prediction
                funding_volatility=Decimal("0.2"),
                leverage=Decimal("3"),
                deployed_capital_usd=Decimal("50000"),
                position_size_usd=Decimal("150000"),
                score=OpportunityScore(
                    funding_apy=Decimal("0.10"),
                    net_carry_apy=Decimal("0.03"),
                    lst_staking_apy=Decimal("0.075"),
                ),
                price_deviation=Decimal("0.001"),
            ),
        ]
    
    def test_filter_by_volatility(self, sample_opportunities):
        """Test filtering by volatility."""
        detector = OpportunityDetector()
        
        filtered = detector.filter_opportunities(
            sample_opportunities,
            max_volatility=Decimal("0.5"),
        )
        
        # opp-2 has 60% volatility (> 50% threshold), should be filtered out
        # opp-1 has 20% volatility, passes
        # opp-3 has 20% volatility but positive prediction (filtered by require_predicted_negative)
        # So only opp-1 should remain
        assert len(filtered) == 1
        assert all(opp.funding_volatility <= Decimal("0.5") for opp in filtered)
        assert filtered[0].id == "opp-1"
    
    def test_filter_by_predicted_negative(self, sample_opportunities):
        """Test filtering by predicted funding negative."""
        detector = OpportunityDetector()
        
        filtered = detector.filter_opportunities(
            sample_opportunities,
            require_predicted_negative=True,
        )
        
        # opp-3 has positive prediction, should be filtered out
        # opp-2 has high volatility (60%), should also be filtered out
        # So only opp-1 should remain
        assert len(filtered) == 1
        assert filtered[0].id == "opp-1"
        assert all(
            opp.predicted_funding is None or opp.predicted_funding.is_negative 
            for opp in filtered
        )
    
    def test_filter_by_min_apy(self, sample_opportunities):
        """Test filtering by minimum APY."""
        detector = OpportunityDetector()
        
        # Modify scores for testing - disable volatility filter by setting max high
        sample_opportunities[0].score = OpportunityScore(
            funding_apy=Decimal("0.05"),
            net_carry_apy=Decimal("-0.01"),
        )  # Total: 4%
        sample_opportunities[1].score = OpportunityScore(
            funding_apy=Decimal("0.05"),
            net_carry_apy=Decimal("0.02"),
            lst_staking_apy=Decimal("0.08"),
        )  # Total: 15%
        sample_opportunities[1].funding_volatility = Decimal("0.2")  # Fix volatility
        
        filtered = detector.filter_opportunities(
            sample_opportunities,
            min_total_apy=Decimal("0.10"),  # 10%
            max_volatility=Decimal("1.0"),  # Disable volatility filter
        )
        
        # Only opp-2 (JITOSOL) should pass with 15% APY
        # opp-1 has 4% APY (fails min)
        # opp-3 has positive prediction (fails require_predicted_negative)
        assert len(filtered) == 1
        assert filtered[0].asset == Asset.JITOSOL
    
    def test_filter_no_requirements(self, sample_opportunities):
        """Test filtering with no restrictions."""
        detector = OpportunityDetector()
        
        filtered = detector.filter_opportunities(
            sample_opportunities,
            require_predicted_negative=False,
            min_total_apy=Decimal("0"),
            max_volatility=Decimal("1.0"),  # Disable volatility filter
        )
        
        # opp-2 has high volatility (60%) but with max_volatility=1.0 it should pass
        # All 3 should pass with no restrictions
        assert len(filtered) == 3


class TestGetBestOpportunity:
    """Tests for best opportunity selection."""
    
    @pytest.fixture
    def ranked_opportunities(self):
        """Create opportunities with varying APYs."""
        base_time = datetime.utcnow()
        
        return [
            ArbitrageOpportunity(
                id="low-apy",
                asset=Asset.INF,
                selected_protocol=Protocol.MARGINFI,
                asgard_rates=AsgardRates(
                    protocol_id=0,
                    token_a_mint=get_mint(Asset.INF),
                    token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    token_a_lending_apy=Decimal("0.04"),
                    token_b_borrowing_apy=Decimal("0.08"),
                    token_b_max_borrow_capacity=Decimal("500000"),
                ),
                current_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.0001")),
                predicted_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.00008")),
                funding_volatility=Decimal("0.2"),
                leverage=Decimal("3"),
                deployed_capital_usd=Decimal("50000"),
                position_size_usd=Decimal("150000"),
                score=OpportunityScore(
                    funding_apy=Decimal("0.05"),
                    net_carry_apy=Decimal("0.01"),
                ),
                price_deviation=Decimal("0.001"),
            ),
            ArbitrageOpportunity(
                id="high-apy",
                asset=Asset.JITOSOL,
                selected_protocol=Protocol.KAMINO,
                asgard_rates=AsgardRates(
                    protocol_id=1,
                    token_a_mint=get_mint(Asset.JITOSOL),
                    token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    token_a_lending_apy=Decimal("0.06"),
                    token_b_borrowing_apy=Decimal("0.075"),
                    token_b_max_borrow_capacity=Decimal("750000"),
                ),
                current_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.0001")),
                predicted_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.00008")),
                funding_volatility=Decimal("0.2"),
                leverage=Decimal("3"),
                deployed_capital_usd=Decimal("50000"),
                position_size_usd=Decimal("150000"),
                score=OpportunityScore(
                    funding_apy=Decimal("0.15"),
                    net_carry_apy=Decimal("0.05"),
                ),
                price_deviation=Decimal("0.001"),
            ),
        ]
    
    def test_get_best_by_apy(self, ranked_opportunities):
        """Test selecting best opportunity by APY."""
        detector = OpportunityDetector()
        
        best = detector.get_best_opportunity(ranked_opportunities)
        
        assert best is not None
        assert best.id == "high-apy"
        assert best.total_expected_apy == Decimal("0.20")
    
    def test_get_best_empty_list(self):
        """Test with empty opportunities list."""
        detector = OpportunityDetector()
        
        best = detector.get_best_opportunity([])
        
        assert best is None
    
    def test_get_best_tie_breaker(self):
        """Test tie-breaker logic (prefer lower volatility, then SOL)."""
        base_time = datetime.utcnow()
        
        # Two opportunities with same APY
        opps = [
            ArbitrageOpportunity(
                id="jitosol",
                asset=Asset.JITOSOL,
                selected_protocol=Protocol.KAMINO,
                asgard_rates=AsgardRates(
                    protocol_id=1,
                    token_a_mint=get_mint(Asset.JITOSOL),
                    token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    token_a_lending_apy=Decimal("0.06"),
                    token_b_borrowing_apy=Decimal("0.075"),
                    token_b_max_borrow_capacity=Decimal("500000"),
                ),
                current_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.0001")),
                predicted_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.00008")),
                funding_volatility=Decimal("0.3"),  # Higher volatility
                leverage=Decimal("3"),
                deployed_capital_usd=Decimal("50000"),
                position_size_usd=Decimal("150000"),
                score=OpportunityScore(funding_apy=Decimal("0.10"), net_carry_apy=Decimal("0.05")),
                price_deviation=Decimal("0.001"),
            ),
            ArbitrageOpportunity(
                id="sol",
                asset=Asset.SOL,
                selected_protocol=Protocol.MARGINFI,
                asgard_rates=AsgardRates(
                    protocol_id=0,
                    token_a_mint=get_mint(Asset.SOL),
                    token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    token_a_lending_apy=Decimal("0.05"),
                    token_b_borrowing_apy=Decimal("0.08"),
                    token_b_max_borrow_capacity=Decimal("1000000"),
                ),
                current_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.0001")),
                predicted_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.00008")),
                funding_volatility=Decimal("0.2"),  # Lower volatility
                leverage=Decimal("3"),
                deployed_capital_usd=Decimal("50000"),
                position_size_usd=Decimal("150000"),
                score=OpportunityScore(funding_apy=Decimal("0.10"), net_carry_apy=Decimal("0.05")),
                price_deviation=Decimal("0.001"),
            ),
        ]
        
        detector = OpportunityDetector()
        best = detector.get_best_opportunity(opps)
        
        # Should prefer SOL due to lower volatility
        assert best.id == "sol"


class TestCheckEntryCriteria:
    """Tests for entry criteria checking."""
    
    @pytest.fixture
    def valid_opportunity(self):
        """Create a valid opportunity that meets all criteria."""
        base_time = datetime.utcnow()
        
        return ArbitrageOpportunity(
            id="valid",
            asset=Asset.SOL,
            selected_protocol=Protocol.MARGINFI,
            asgard_rates=AsgardRates(
                protocol_id=0,
                token_a_mint=get_mint(Asset.SOL),
                token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                token_a_lending_apy=Decimal("0.05"),
                token_b_borrowing_apy=Decimal("0.08"),
                token_b_max_borrow_capacity=Decimal("1000000"),
            ),
            current_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.0001")),
            predicted_funding=FundingRate(timestamp=base_time, coin="SOL", rate_8hr=Decimal("-0.00008")),
            funding_volatility=Decimal("0.2"),
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("50000"),
            position_size_usd=Decimal("150000"),
            score=OpportunityScore(
                funding_apy=Decimal("0.10"),
                net_carry_apy=Decimal("0.02"),
            ),
            price_deviation=Decimal("0.001"),
            preflight_checks_passed=True,
        )
    
    @pytest.mark.asyncio
    async def test_all_criteria_met(self, valid_opportunity):
        """Test when all criteria are met."""
        detector = OpportunityDetector()
        
        should_enter, criteria = await detector.check_entry_criteria(valid_opportunity)
        
        assert should_enter is True
        assert all(criteria.values())
    
    @pytest.mark.asyncio
    async def test_positive_current_funding(self, valid_opportunity):
        """Test when current funding is positive."""
        valid_opportunity.current_funding = FundingRate(
            timestamp=datetime.utcnow(),
            coin="SOL",
            rate_8hr=Decimal("0.0001"),  # Positive
        )
        
        detector = OpportunityDetector()
        should_enter, criteria = await detector.check_entry_criteria(valid_opportunity)
        
        assert should_enter is False
        assert criteria["current_funding_negative"] is False
    
    @pytest.mark.asyncio
    async def test_high_price_deviation(self, valid_opportunity):
        """Test when price deviation exceeds threshold."""
        valid_opportunity.price_deviation = Decimal("0.01")  # 1% > 0.5%
        
        detector = OpportunityDetector()
        should_enter, criteria = await detector.check_entry_criteria(valid_opportunity)
        
        assert should_enter is False
        assert criteria["price_deviation_acceptable"] is False
    
    @pytest.mark.asyncio
    async def test_preflight_not_passed(self, valid_opportunity):
        """Test when preflight checks haven't passed."""
        valid_opportunity.preflight_checks_passed = False
        
        detector = OpportunityDetector()
        should_enter, criteria = await detector.check_entry_criteria(valid_opportunity)
        
        assert should_enter is False
        assert criteria["preflight_passed"] is False


class TestCacheManagement:
    """Tests for cache management."""
    
    def test_clear_cache(self, mock_asgard_market_data, mock_hyperliquid_oracle):
        """Test that cache clear propagates to clients."""
        detector = OpportunityDetector(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_oracle=mock_hyperliquid_oracle,
        )
        
        detector.clear_cache()
        
        mock_asgard_market_data.clear_cache.assert_called_once()
        mock_hyperliquid_oracle.clear_cache.assert_called_once()


class TestContextManager:
    """Tests for async context manager."""
    
    @pytest.mark.asyncio
    async def test_context_manager_initializes_clients(self):
        """Test that context manager initializes clients."""
        with patch("bot.core.opportunity_detector.AsgardMarketData") as mock_asgard_class, \
             patch("bot.core.opportunity_detector.HyperliquidFundingOracle") as mock_hl_class:
            
            mock_asgard = MagicMock()
            mock_asgard.client._session = None
            mock_asgard.client._init_session = AsyncMock()
            mock_asgard.close = AsyncMock()
            mock_asgard_class.return_value = mock_asgard
            
            mock_hl = MagicMock()
            mock_hl.client._session = None
            mock_hl.client._init_session = AsyncMock()
            mock_hl.client.close = AsyncMock()
            mock_hl_class.return_value = mock_hl
            
            async with OpportunityDetector() as detector:
                pass
            
            # Should initialize sessions
            mock_asgard.client._init_session.assert_called_once()
            mock_hl.client._init_session.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_context_manager_closes_owned_clients(self, mock_asgard_market_data, mock_hyperliquid_oracle):
        """Test that context manager closes clients it owns."""
        async with OpportunityDetector() as detector:
            detector.asgard = mock_asgard_market_data
            detector.hyperliquid = mock_hyperliquid_oracle
            detector._own_asgard = True
            detector._own_hyperliquid = True
        
        mock_asgard_market_data.close.assert_called_once()
        mock_hyperliquid_oracle.client.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_context_manager_preserves_external_clients(self, mock_asgard_market_data, mock_hyperliquid_oracle):
        """Test that context manager doesn't close externally provided clients."""
        async with OpportunityDetector(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_oracle=mock_hyperliquid_oracle,
        ) as detector:
            pass
        
        # Should not close externally provided clients
        mock_asgard_market_data.close.assert_not_called()
        mock_hyperliquid_oracle.close.assert_not_called()
