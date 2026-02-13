"""
Tests for Price Consensus module.

These tests verify:
- Price fetching from both venues
- Deviation calculation
- Threshold enforcement
- Concurrent price fetching
- Error handling
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.config.assets import Asset
from bot.core.price_consensus import (
    ConsensusResult,
    PriceConsensus,
    PriceDeviationError,
)
from bot.venues.asgard.market_data import AsgardMarketData
from bot.venues.hyperliquid.client import HyperliquidClient


# Fixtures
@pytest.fixture
def mock_asgard_market_data():
    """Mock AsgardMarketData."""
    mock = MagicMock(spec=AsgardMarketData)
    mock.client = MagicMock()
    mock.client._session = MagicMock()
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_hyperliquid_client():
    """Mock HyperliquidClient."""
    mock = MagicMock(spec=HyperliquidClient)
    mock._session = MagicMock()
    mock.close = AsyncMock()
    mock._init_session = AsyncMock()
    return mock


def _make_asgard_markets(token_a_mint, oracle_price, strategy_name="SOL-USDC"):
    """Build Asgard markets response in the strategies dict format."""
    return {
        "strategies": {
            strategy_name: {
                "tokenAMint": token_a_mint,
                "tokenBMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "oraclePrice": oracle_price,
            }
        }
    }


def _make_hl_contexts(coin, mark_px, oracle_px=None):
    """Build Hyperliquid metaAndAssetCtxs response (list format)."""
    ctx = {"markPx": str(mark_px)}
    if oracle_px is not None:
        ctx["oraclePx"] = str(oracle_px)
    return [
        {"universe": [{"name": coin}]},
        [ctx],
    ]


class TestPriceConsensusInit:
    """Tests for PriceConsensus initialization."""

    def test_init_with_clients(self, mock_asgard_market_data, mock_hyperliquid_client):
        """Test initialization with provided clients."""
        consensus = PriceConsensus(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_client=mock_hyperliquid_client,
            max_deviation=Decimal("0.01"),
        )

        assert consensus.asgard is mock_asgard_market_data
        assert consensus.hyperliquid is mock_hyperliquid_client
        assert consensus.max_deviation == Decimal("0.01")
        assert not consensus._own_asgard
        assert not consensus._own_hyperliquid

    def test_init_default_values(self):
        """Test initialization with default values."""
        consensus = PriceConsensus()

        assert consensus.asgard is None
        assert consensus.hyperliquid is None
        assert consensus.max_deviation == PriceConsensus.MAX_PRICE_DEVIATION
        assert consensus._own_asgard
        assert consensus._own_hyperliquid

    def test_max_deviation_default(self):
        """Test default max deviation is 0.5%."""
        consensus = PriceConsensus()
        assert consensus.max_deviation == Decimal("0.005")


class TestCheckConsensus:
    """Tests for price consensus checking."""

    @pytest.mark.asyncio
    async def test_consensus_within_threshold(
        self, mock_asgard_market_data, mock_hyperliquid_client
    ):
        """Test when prices are within threshold."""
        sol_mint = "So11111111111111111111111111111111111111112"
        mock_asgard_market_data.get_markets = AsyncMock(
            return_value=_make_asgard_markets(sol_mint, 100.0)
        )
        mock_hyperliquid_client.get_meta_and_asset_contexts = AsyncMock(
            return_value=_make_hl_contexts("SOL", 100.5)
        )

        consensus = PriceConsensus(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_client=mock_hyperliquid_client,
        )

        result = await consensus.check_consensus(Asset.SOL)

        assert result.is_within_threshold is True
        assert result.asgard_price == Decimal("100")
        assert result.hyperliquid_price == Decimal("100.5")
        assert result.asset == Asset.SOL

    @pytest.mark.asyncio
    async def test_consensus_exceeds_threshold(
        self, mock_asgard_market_data, mock_hyperliquid_client
    ):
        """Test when prices exceed threshold."""
        sol_mint = "So11111111111111111111111111111111111111112"
        mock_asgard_market_data.get_markets = AsyncMock(
            return_value=_make_asgard_markets(sol_mint, 100.0)
        )
        mock_hyperliquid_client.get_meta_and_asset_contexts = AsyncMock(
            return_value=_make_hl_contexts("SOL", 102.0)
        )

        consensus = PriceConsensus(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_client=mock_hyperliquid_client,
        )

        result = await consensus.check_consensus(Asset.SOL)

        assert result.is_within_threshold is False

    @pytest.mark.asyncio
    async def test_consensus_asgard_higher(
        self, mock_asgard_market_data, mock_hyperliquid_client
    ):
        """Test when Asgard price is higher than Hyperliquid."""
        sol_mint = "So11111111111111111111111111111111111111112"
        mock_asgard_market_data.get_markets = AsyncMock(
            return_value=_make_asgard_markets(sol_mint, 105.0)
        )
        mock_hyperliquid_client.get_meta_and_asset_contexts = AsyncMock(
            return_value=_make_hl_contexts("SOL", 100.0)
        )

        consensus = PriceConsensus(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_client=mock_hyperliquid_client,
        )

        result = await consensus.check_consensus(Asset.SOL)

        assert result.price_divergence == "asgard_higher"
        assert result.asgard_price > result.hyperliquid_price

    @pytest.mark.asyncio
    async def test_consensus_hyperliquid_higher(
        self, mock_asgard_market_data, mock_hyperliquid_client
    ):
        """Test when Hyperliquid price is higher than Asgard."""
        sol_mint = "So11111111111111111111111111111111111111112"
        mock_asgard_market_data.get_markets = AsyncMock(
            return_value=_make_asgard_markets(sol_mint, 100.0)
        )
        mock_hyperliquid_client.get_meta_and_asset_contexts = AsyncMock(
            return_value=_make_hl_contexts("SOL", 105.0)
        )

        consensus = PriceConsensus(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_client=mock_hyperliquid_client,
        )

        result = await consensus.check_consensus(Asset.SOL)

        assert result.price_divergence == "hyperliquid_higher"
        assert result.hyperliquid_price > result.asgard_price


class TestDeviationCalculation:
    """Tests for deviation calculation."""

    def test_calculate_deviation_equal_prices(self):
        """Test deviation with equal prices."""
        consensus = PriceConsensus()
        dev = consensus._calculate_deviation(Decimal("100"), Decimal("100"))
        assert dev == Decimal("0")

    def test_calculate_deviation_positive(self):
        """Test deviation calculation."""
        consensus = PriceConsensus()
        dev = consensus._calculate_deviation(Decimal("100"), Decimal("101"))
        assert dev == pytest.approx(Decimal("0.00995"), abs=Decimal("0.0001"))

    def test_calculate_deviation_zero_price(self):
        """Test deviation with zero price."""
        consensus = PriceConsensus()
        dev = consensus._calculate_deviation(Decimal("0"), Decimal("100"))
        assert dev == Decimal("1")  # 100% deviation

    def test_calculate_deviation_both_zero(self):
        """Test deviation when both prices are zero."""
        consensus = PriceConsensus()
        dev = consensus._calculate_deviation(Decimal("0"), Decimal("0"))
        assert dev == Decimal("0")


class TestConsensusResult:
    """Tests for ConsensusResult dataclass."""

    def test_consensus_price_calculation(self):
        """Test consensus price is average."""
        result = ConsensusResult(
            asgard_price=Decimal("100"),
            hyperliquid_price=Decimal("102"),
            price_deviation=Decimal("0.02"),
            deviation_percent=Decimal("0.02"),
            asset=Asset.SOL,
            is_within_threshold=False,
            threshold=Decimal("0.005"),
        )

        assert result.consensus_price == Decimal("101")

    def test_price_divergence_equal(self):
        """Test divergence when prices are equal."""
        result = ConsensusResult(
            asgard_price=Decimal("100"),
            hyperliquid_price=Decimal("100"),
            price_deviation=Decimal("0"),
            deviation_percent=Decimal("0"),
            asset=Asset.SOL,
            is_within_threshold=True,
            threshold=Decimal("0.005"),
        )

        assert result.price_divergence == "equal"

    def test_to_summary(self):
        """Test summary dict generation."""
        result = ConsensusResult(
            asgard_price=Decimal("100"),
            hyperliquid_price=Decimal("101"),
            price_deviation=Decimal("0.01"),
            deviation_percent=Decimal("0.01"),
            asset=Asset.SOL,
            is_within_threshold=True,
            threshold=Decimal("0.005"),
        )

        summary = result.to_summary()

        assert summary["asset"] == "SOL"
        assert summary["asgard_price"] == 100.0
        assert summary["hyperliquid_price"] == 101.0
        assert summary["deviation"] == 0.01
        assert summary["deviation_bps"] == 100.0  # 1% = 100 bps
        assert summary["within_threshold"] is True


class TestSlippageCalculation:
    """Tests for slippage-adjusted price calculation."""

    def test_slippage_adjusted_prices(self):
        """Test worst-case price calculation with slippage."""
        consensus = PriceConsensus()

        result = ConsensusResult(
            asgard_price=Decimal("100"),
            hyperliquid_price=Decimal("100"),
            price_deviation=Decimal("0"),
            deviation_percent=Decimal("0"),
            asset=Asset.SOL,
            is_within_threshold=True,
            threshold=Decimal("0.005"),
        )

        worst_long, worst_short = consensus.calculate_slippage_adjusted_prices(
            result,
            slippage_bps=Decimal("50"),  # 0.5%
        )

        assert worst_long == Decimal("100.5")
        assert worst_short == Decimal("99.5")


class TestContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_initializes_clients(self):
        """Test that context manager initializes clients."""
        with patch("bot.core.price_consensus.AsgardMarketData") as mock_asgard_class, \
             patch("bot.core.price_consensus.HyperliquidClient") as mock_hl_class:

            mock_asgard = MagicMock()
            mock_asgard.client._session = None
            mock_asgard.client._init_session = AsyncMock()
            mock_asgard.close = AsyncMock()
            mock_asgard_class.return_value = mock_asgard

            mock_hl = MagicMock()
            mock_hl._session = None
            mock_hl._init_session = AsyncMock()
            mock_hl.close = AsyncMock()
            mock_hl_class.return_value = mock_hl

            async with PriceConsensus() as consensus:
                pass

            mock_asgard.client._init_session.assert_called_once()
            mock_hl._init_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_closes_owned_clients(self, mock_asgard_market_data, mock_hyperliquid_client):
        """Test that context manager closes owned clients."""
        async with PriceConsensus() as consensus:
            consensus.asgard = mock_asgard_market_data
            consensus.hyperliquid = mock_hyperliquid_client
            consensus._own_asgard = True
            consensus._own_hyperliquid = True

        mock_asgard_market_data.close.assert_called_once()
        mock_hyperliquid_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_preserves_external_clients(self, mock_asgard_market_data, mock_hyperliquid_client):
        """Test that external clients are not closed."""
        async with PriceConsensus(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_client=mock_hyperliquid_client,
        ) as consensus:
            pass

        mock_asgard_market_data.close.assert_not_called()
        mock_hyperliquid_client.close.assert_not_called()


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_hyperliquid_coin_not_found(self, mock_asgard_market_data, mock_hyperliquid_client):
        """Test handling when coin not found on Hyperliquid."""
        sol_mint = "So11111111111111111111111111111111111111112"
        mock_asgard_market_data.get_markets = AsyncMock(
            return_value=_make_asgard_markets(sol_mint, 100.0)
        )
        # BTC in universe but we query SOL
        mock_hyperliquid_client.get_meta_and_asset_contexts = AsyncMock(
            return_value=[
                {"universe": [{"name": "BTC"}]},
                [{"markPx": "50000"}],
            ]
        )

        consensus = PriceConsensus(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_client=mock_hyperliquid_client,
        )

        with pytest.raises(ValueError, match="Coin SOL not found"):
            await consensus.check_consensus(Asset.SOL)

    @pytest.mark.asyncio
    async def test_asgard_price_found(self, mock_asgard_market_data, mock_hyperliquid_client):
        """Test that Asgard price is found via token mint match."""
        sol_mint = "So11111111111111111111111111111111111111112"
        mock_asgard_market_data.get_markets = AsyncMock(
            return_value=_make_asgard_markets(sol_mint, 100.0)
        )
        mock_hyperliquid_client.get_meta_and_asset_contexts = AsyncMock(
            return_value=_make_hl_contexts("SOL", 100.0)
        )

        consensus = PriceConsensus(
            asgard_market_data=mock_asgard_market_data,
            hyperliquid_client=mock_hyperliquid_client,
        )

        result = await consensus.check_consensus(Asset.SOL)

        assert result.asgard_price == Decimal("100")
