"""
Tests for Asgard Market Data module.

These tests verify:
- Market data fetching and caching
- Borrowing rate extraction
- Net carry calculation
- Protocol selection with capacity checks

Mock data uses the real API response format (strategies with liquiditySources).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.config.assets import Asset, get_mint
from shared.models.common import Protocol
from bot.venues.asgard.client import AsgardClient
from bot.venues.asgard.market_data import (
    AsgardMarketData,
    NetCarryResult,
    ProtocolRate,
)

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINT = "So11111111111111111111111111111111111111112"


@pytest.fixture
def mock_markets_response():
    """Sample markets API response in real Asgard format."""
    return {
        "strategies": {
            "SOL/USDC": {
                "name": "SOL/USDC",
                "description": "SOL margin trading",
                "tokenAMint": SOL_MINT,
                "tokenBMint": USDC_MINT,
                "market": ["MARGIN"],
                "tag": ["TRADING"],
                "liquiditySources": [
                    {
                        "lendingProtocol": 0,  # Marginfi
                        "isActive": True,
                        "tokenABank": "marginfi_sol_bank",
                        "tokenBBank": "marginfi_usdc_bank",
                        "longMaxLeverage": 4.0,
                        "shortMaxLeverage": 3.0,
                        "tokenALendingApyRate": 0.05,
                        "tokenBBorrowingApyRate": 0.08,
                        "tokenBMaxBorrowCapacity": "1000000",
                        "tokenAMaxDepositCapacity": "5000000",
                    },
                    {
                        "lendingProtocol": 1,  # Kamino
                        "isActive": True,
                        "tokenABank": "kamino_sol_bank",
                        "tokenBBank": "kamino_usdc_bank",
                        "longMaxLeverage": 3.8,
                        "shortMaxLeverage": 2.5,
                        "tokenALendingApyRate": 0.055,
                        "tokenBBorrowingApyRate": 0.075,
                        "tokenBMaxBorrowCapacity": "500000",
                        "tokenAMaxDepositCapacity": "3000000",
                    },
                    {
                        "lendingProtocol": 2,  # Solend
                        "isActive": True,
                        "tokenABank": "solend_sol_bank",
                        "tokenBBank": "solend_usdc_bank",
                        "longMaxLeverage": 4.0,
                        "shortMaxLeverage": 3.0,
                        "tokenALendingApyRate": 0.04,
                        "tokenBBorrowingApyRate": 0.09,
                        "tokenBMaxBorrowCapacity": "2000000",
                        "tokenAMaxDepositCapacity": "8000000",
                    },
                ],
            },
        },
        "totalStrategies": 1,
    }


class TestAsgardMarketDataInit:
    """Tests for market data initialization."""

    def test_init_with_client(self):
        """Test initialization with provided client."""
        client = MagicMock(spec=AsgardClient)
        market_data = AsgardMarketData(client=client)
        assert market_data.client is client

    @patch("bot.venues.asgard.market_data.AsgardClient")
    def test_init_creates_client(self, mock_client_class):
        """Test that client is created if not provided."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        market_data = AsgardMarketData()
        assert market_data.client is mock_client


class TestGetMarkets:
    """Tests for fetching market data."""

    @pytest.mark.asyncio
    async def test_get_markets_parses_response(self, mock_markets_response):
        """Test that strategies are fetched and parsed correctly."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        response = await market_data.get_markets(use_cache=False)

        strategies = response.get("strategies", {})
        assert len(strategies) == 1
        assert "SOL/USDC" in strategies
        assert len(strategies["SOL/USDC"]["liquiditySources"]) == 3

    @pytest.mark.asyncio
    async def test_get_markets_uses_cache(self, mock_markets_response):
        """Test that cached data is returned when use_cache=True."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        # First call should fetch
        await market_data.get_markets(use_cache=True)

        # Modify cache to verify second call uses cache
        cached = {"strategies": {"cached": True}, "totalStrategies": 0}
        market_data._strategies_cache = cached

        # Second call should use cache
        result = await market_data.get_markets(use_cache=True)

        assert result is cached
        # get_markets should only be called once
        client.get_markets.assert_called_once()


class TestGetBorrowingRates:
    """Tests for borrowing rate extraction."""

    @pytest.mark.asyncio
    async def test_get_rates_for_sol(self, mock_markets_response):
        """Test extracting rates for SOL."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        rates = await market_data.get_borrowing_rates(SOL_MINT)

        # Should have 3 protocols for SOL/USDC
        assert len(rates) == 3

        # Check first protocol (Marginfi, sorted by protocol ID)
        assert rates[0].protocol == Protocol.MARGINFI
        assert rates[0].lending_rate == 0.05
        assert rates[0].borrowing_rate == 0.08
        assert rates[0].max_borrow_capacity == 1000000
        assert rates[0].token_a_bank == "marginfi_sol_bank"
        assert rates[0].token_b_bank == "marginfi_usdc_bank"

        # Check second protocol (Kamino)
        assert rates[1].protocol == Protocol.KAMINO
        assert rates[1].lending_rate == 0.055

        # Check third protocol (Solend)
        assert rates[2].protocol == Protocol.SOLEND

    @pytest.mark.asyncio
    async def test_get_rates_returns_empty_for_unknown_token(self, mock_markets_response):
        """Test that empty list is returned for unknown token."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        rates = await market_data.get_borrowing_rates("UnknownMint123")

        assert rates == []

    @pytest.mark.asyncio
    async def test_skips_inactive_sources(self):
        """Test that inactive liquidity sources are filtered out."""
        response = {
            "strategies": {
                "SOL/USDC": {
                    "tokenAMint": SOL_MINT,
                    "tokenBMint": USDC_MINT,
                    "liquiditySources": [
                        {
                            "lendingProtocol": 0,
                            "isActive": False,  # inactive
                            "tokenABank": "bank_a",
                            "tokenBBank": "bank_b",
                            "longMaxLeverage": 4.0,
                            "tokenALendingApyRate": 0.05,
                            "tokenBBorrowingApyRate": 0.08,
                            "tokenBMaxBorrowCapacity": "1000000",
                        },
                        {
                            "lendingProtocol": 1,
                            "isActive": True,
                            "tokenABank": "bank_a2",
                            "tokenBBank": "bank_b2",
                            "longMaxLeverage": 3.8,
                            "tokenALendingApyRate": 0.04,
                            "tokenBBorrowingApyRate": 0.07,
                            "tokenBMaxBorrowCapacity": "500000",
                        },
                    ],
                },
            },
        }

        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=response)
        market_data = AsgardMarketData(client=client)

        rates = await market_data.get_borrowing_rates(SOL_MINT)
        assert len(rates) == 1
        assert rates[0].protocol == Protocol.KAMINO


class TestCalculateNetCarry:
    """Tests for net carry calculation."""

    @pytest.mark.asyncio
    async def test_net_carry_calculation_3x(self, mock_markets_response):
        """Test net carry calculation at 3x leverage."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        result = await market_data.calculate_net_carry_apy(
            protocol=Protocol.MARGINFI,
            token_a_mint=SOL_MINT,
            leverage=3.0,
        )

        assert result is not None
        assert result.protocol == Protocol.MARGINFI
        assert result.lending_rate == 0.05
        assert result.borrowing_rate == 0.08

        # Net carry = (3 x 0.05) - (2 x 0.08) = 0.15 - 0.16 = -0.01
        assert result.net_carry_apy == pytest.approx(-0.01)
        assert result.leverage == 3.0

    @pytest.mark.asyncio
    async def test_net_carry_calculation_4x(self, mock_markets_response):
        """Test net carry calculation at 4x leverage."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        result = await market_data.calculate_net_carry_apy(
            protocol=Protocol.MARGINFI,
            token_a_mint=SOL_MINT,
            leverage=4.0,
        )

        # Net carry = (4 x 0.05) - (3 x 0.08) = 0.20 - 0.24 = -0.04
        assert result.net_carry_apy == pytest.approx(-0.04)

    @pytest.mark.asyncio
    async def test_net_carry_for_nonexistent_protocol(self, mock_markets_response):
        """Test that None is returned for non-existent protocol."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        result = await market_data.calculate_net_carry_apy(
            protocol=Protocol.DRIFT,  # Not in mock data
            token_a_mint=SOL_MINT,
            leverage=3.0,
        )

        assert result is None


class TestSelectBestProtocol:
    """Tests for protocol selection."""

    @pytest.mark.asyncio
    async def test_selects_best_net_carry(self, mock_markets_response):
        """Test that protocol with best net carry is selected."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        # Small position that all protocols can handle
        result = await market_data.select_best_protocol(
            asset=Asset.SOL,
            size_usd=10000,  # $10k
            leverage=3.0,
        )

        assert result is not None
        # Kamino should have best net carry:
        # Marginfi: (3 x 0.05) - (2 x 0.08) = -0.01
        # Kamino: (3 x 0.055) - (2 x 0.075) = 0.015
        # Solend: (3 x 0.04) - (2 x 0.09) = -0.06
        assert result.protocol == Protocol.KAMINO
        assert result.net_carry_apy == pytest.approx(0.015)

    @pytest.mark.asyncio
    async def test_respects_capacity_limits(self, mock_markets_response):
        """Test that protocols without capacity are filtered out."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        # Large position requiring $400k+ borrow capacity (with 1.2 buffer)
        result = await market_data.select_best_protocol(
            asset=Asset.SOL,
            size_usd=200000,  # $200k
            leverage=3.0,
            safety_buffer=1.2,
        )

        # Required capacity: $200k x 2 x 1.2 = $480k
        # Kamino ($500k) - has capacity
        # Marginfi ($1M) - has capacity
        # Solend ($2M) - has capacity
        assert result is not None
        assert result.has_capacity is True

    @pytest.mark.asyncio
    async def test_respects_max_leverage(self):
        """Test that protocols with insufficient max leverage are filtered out."""
        response = {
            "strategies": {
                "SOL/USDC": {
                    "tokenAMint": SOL_MINT,
                    "tokenBMint": USDC_MINT,
                    "liquiditySources": [
                        {
                            "lendingProtocol": 1,
                            "isActive": True,
                            "tokenABank": "bank_a",
                            "tokenBBank": "bank_b",
                            "longMaxLeverage": 2.0,  # Too low for 3x
                            "tokenALendingApyRate": 0.10,
                            "tokenBBorrowingApyRate": 0.03,
                            "tokenBMaxBorrowCapacity": "1000000",
                        },
                        {
                            "lendingProtocol": 3,
                            "isActive": True,
                            "tokenABank": "bank_a2",
                            "tokenBBank": "bank_b2",
                            "longMaxLeverage": 5.0,  # Supports 3x
                            "tokenALendingApyRate": 0.08,
                            "tokenBBorrowingApyRate": 0.04,
                            "tokenBMaxBorrowCapacity": "1000000",
                        },
                    ],
                },
            },
        }

        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=response)
        market_data = AsgardMarketData(client=client)

        result = await market_data.select_best_protocol(
            asset=Asset.SOL, size_usd=10000, leverage=3.0
        )

        # Should pick Drift (proto 3) since Kamino's max leverage is 2.0 < 3.0
        assert result is not None
        assert result.protocol == Protocol.DRIFT

    @pytest.mark.asyncio
    async def test_tie_breaker_by_protocol_order(self):
        """Test that tie is broken by protocol order."""
        tied_response = {
            "strategies": {
                "SOL/USDC": {
                    "tokenAMint": SOL_MINT,
                    "tokenBMint": USDC_MINT,
                    "liquiditySources": [
                        {
                            "lendingProtocol": 0,
                            "isActive": True,
                            "tokenABank": "bank_a",
                            "tokenBBank": "bank_b",
                            "longMaxLeverage": 4.0,
                            "tokenALendingApyRate": 0.05,
                            "tokenBBorrowingApyRate": 0.075,
                            "tokenBMaxBorrowCapacity": "1000000",
                        },
                        {
                            "lendingProtocol": 1,
                            "isActive": True,
                            "tokenABank": "bank_a2",
                            "tokenBBank": "bank_b2",
                            "longMaxLeverage": 4.0,
                            "tokenALendingApyRate": 0.05,
                            "tokenBBorrowingApyRate": 0.075,
                            "tokenBMaxBorrowCapacity": "1000000",
                        },
                    ],
                },
            },
        }

        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=tied_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        result = await market_data.select_best_protocol(
            asset=Asset.SOL, size_usd=10000, leverage=3.0,
        )

        # Should select Marginfi (protocol 0) over Kamino (protocol 1)
        assert result.protocol == Protocol.MARGINFI

    @pytest.mark.asyncio
    async def test_returns_none_if_no_protocol_has_capacity(self, mock_markets_response):
        """Test that None is returned if no protocol has capacity."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        # Very large position requiring more than any protocol can handle
        result = await market_data.select_best_protocol(
            asset=Asset.SOL,
            size_usd=10000000,  # $10M
            leverage=3.0,
        )

        assert result is None


class TestCacheManagement:
    """Tests for cache management."""

    @pytest.mark.asyncio
    async def test_clear_cache(self, mock_markets_response):
        """Test that cache can be cleared."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()

        market_data = AsgardMarketData(client=client)

        # Populate cache
        await market_data.get_markets()
        await market_data.get_borrowing_rates(SOL_MINT)

        assert market_data._strategies_cache is not None
        assert market_data._rates_cache is not None

        # Clear cache
        market_data.clear_cache()

        assert market_data._strategies_cache is None
        assert market_data._rates_cache is None
