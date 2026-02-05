"""
Tests for Asgard Market Data module.

These tests verify:
- Market data fetching and caching
- Borrowing rate extraction
- Net carry calculation
- Protocol selection with capacity checks
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config.assets import Asset, get_mint
from src.models.common import Protocol
from src.venues.asgard.client import AsgardClient
from src.venues.asgard.market_data import (
    AsgardMarketData,
    NetCarryResult,
    ProtocolRate,
)


# Mock market data fixtures
@pytest.fixture
def mock_markets_response():
    """Sample markets API response."""
    return {
        "markets": [
            {
                "strategy": "SOL-USDC",
                "protocol": 0,  # Marginfi
                "tokenAMint": "So11111111111111111111111111111111111111112",
                "tokenBMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "lendingRate": 0.05,  # 5%
                "borrowingRate": 0.08,  # 8%
                "tokenBMaxBorrowCapacity": 1000000,  # $1M
            },
            {
                "strategy": "SOL-USDC",
                "protocol": 1,  # Kamino
                "tokenAMint": "So11111111111111111111111111111111111111112",
                "tokenBMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "lendingRate": 0.055,  # 5.5%
                "borrowingRate": 0.075,  # 7.5%
                "tokenBMaxBorrowCapacity": 500000,  # $500k
            },
            {
                "strategy": "SOL-USDC",
                "protocol": 2,  # Solend
                "tokenAMint": "So11111111111111111111111111111111111111112",
                "tokenBMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "lendingRate": 0.04,  # 4%
                "borrowingRate": 0.09,  # 9%
                "tokenBMaxBorrowCapacity": 2000000,  # $2M
            },
            {
                "strategy": "jitoSOL-USDC",
                "protocol": 0,  # Marginfi
                "tokenAMint": "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v",
                "tokenBMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "lendingRate": 0.06,
                "borrowingRate": 0.085,
                "tokenBMaxBorrowCapacity": 750000,
            },
        ]
    }


class TestAsgardMarketDataInit:
    """Tests for market data initialization."""
    
    def test_init_with_client(self):
        """Test initialization with provided client."""
        client = MagicMock(spec=AsgardClient)
        market_data = AsgardMarketData(client=client)
        assert market_data.client is client
    
    @patch("src.venues.asgard.market_data.AsgardClient")
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
        """Test that markets are fetched and parsed correctly."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()
        
        market_data = AsgardMarketData(client=client)
        
        markets = await market_data.get_markets(use_cache=False)
        
        assert len(markets) == 4
        assert markets[0]["strategy"] == "SOL-USDC"
        assert markets[0]["protocol"] == 0
    
    @pytest.mark.asyncio
    async def test_get_markets_uses_cache(self, mock_markets_response):
        """Test that cached data is returned when use_cache=True."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()
        
        market_data = AsgardMarketData(client=client)
        
        # First call should fetch
        markets1 = await market_data.get_markets(use_cache=True)
        
        # Modify cache to verify second call uses cache
        market_data._markets_cache = [{"cached": True}]
        
        # Second call should use cache
        markets2 = await market_data.get_markets(use_cache=True)
        
        assert markets2 == [{"cached": True}]
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
        
        sol_mint = "So11111111111111111111111111111111111111112"
        rates = await market_data.get_borrowing_rates(sol_mint)
        
        # Should have 3 protocols for SOL
        assert len(rates) == 3
        
        # Check first protocol (Marginfi)
        assert rates[0].protocol == Protocol.MARGINFI
        assert rates[0].lending_rate == 0.05
        assert rates[0].borrowing_rate == 0.08
        
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
        
        sol_mint = "So11111111111111111111111111111111111111112"
        result = await market_data.calculate_net_carry_apy(
            protocol=Protocol.MARGINFI,
            token_a_mint=sol_mint,
            leverage=3.0,
        )
        
        assert result is not None
        assert result.protocol == Protocol.MARGINFI
        assert result.lending_rate == 0.05
        assert result.borrowing_rate == 0.08
        
        # Net carry = (3 × 0.05) - (2 × 0.08) = 0.15 - 0.16 = -0.01
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
        
        sol_mint = "So11111111111111111111111111111111111111112"
        result = await market_data.calculate_net_carry_apy(
            protocol=Protocol.MARGINFI,
            token_a_mint=sol_mint,
            leverage=4.0,
        )
        
        # Net carry = (4 × 0.05) - (3 × 0.08) = 0.20 - 0.24 = -0.04
        assert result.net_carry_apy == pytest.approx(-0.04)
    
    @pytest.mark.asyncio
    async def test_net_carry_for_nonexistent_protocol(self, mock_markets_response):
        """Test that None is returned for non-existent protocol."""
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=mock_markets_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()
        
        market_data = AsgardMarketData(client=client)
        
        sol_mint = "So11111111111111111111111111111111111111112"
        result = await market_data.calculate_net_carry_apy(
            protocol=Protocol.DRIFT,  # Not in mock data
            token_a_mint=sol_mint,
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
        # Marginfi: (3 × 0.05) - (2 × 0.08) = -0.01
        # Kamino: (3 × 0.055) - (2 × 0.075) = 0.015
        # Solend: (3 × 0.04) - (2 × 0.09) = -0.06
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
        # Kamino only has $500k capacity, may not have enough
        result = await market_data.select_best_protocol(
            asset=Asset.SOL,
            size_usd=200000,  # $200k
            leverage=3.0,
            safety_buffer=1.2,
        )
        
        # Required capacity: $200k × 2 × 1.2 = $480k
        # Kamino ($500k) - has capacity but barely
        # Marginfi ($1M) - has capacity
        # Solend ($2M) - has capacity
        assert result is not None
        assert result.has_capacity is True
    
    @pytest.mark.asyncio
    async def test_tie_breaker_by_protocol_order(self, mock_markets_response):
        """Test that tie is broken by protocol order."""
        # Modify mock to create tie
        tied_response = {
            "markets": [
                {
                    "strategy": "SOL-USDC",
                    "protocol": 0,  # Marginfi
                    "tokenAMint": "So11111111111111111111111111111111111111112",
                    "tokenBMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    "lendingRate": 0.05,
                    "borrowingRate": 0.075,  # Same as Kamino below
                    "tokenBMaxBorrowCapacity": 1000000,
                },
                {
                    "strategy": "SOL-USDC",
                    "protocol": 1,  # Kamino
                    "tokenAMint": "So11111111111111111111111111111111111111112",
                    "tokenBMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    "lendingRate": 0.05,
                    "borrowingRate": 0.075,  # Same net carry as Marginfi
                    "tokenBMaxBorrowCapacity": 1000000,
                },
            ]
        }
        
        client = MagicMock(spec=AsgardClient)
        client.get_markets = AsyncMock(return_value=tied_response)
        client._init_session = AsyncMock()
        client.close = AsyncMock()
        
        market_data = AsgardMarketData(client=client)
        
        result = await market_data.select_best_protocol(
            asset=Asset.SOL,
            size_usd=10000,
            leverage=3.0,
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
        await market_data.get_borrowing_rates("So11111111111111111111111111111111111111112")
        
        assert market_data._markets_cache is not None
        assert market_data._rates_cache is not None
        
        # Clear cache
        market_data.clear_cache()
        
        assert market_data._markets_cache is None
        assert market_data._rates_cache is None
