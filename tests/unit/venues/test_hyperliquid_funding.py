"""
Tests for Hyperliquid Funding Oracle.

These tests verify:
- Current funding rate fetching
- Funding history retrieval
- Funding prediction
- Volatility calculation
- Entry criteria checking
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.venues.hyperliquid.client import HyperliquidClient
from src.venues.hyperliquid.funding_oracle import (
    HyperliquidFundingOracle,
    FundingRate,
    FundingPrediction,
)


class TestFundingOracleInit:
    """Tests for funding oracle initialization."""
    
    def test_init_with_client(self):
        """Test initialization with provided client."""
        client = MagicMock(spec=HyperliquidClient)
        oracle = HyperliquidFundingOracle(client=client)
        assert oracle.client is client
    
    @patch("src.venues.hyperliquid.funding_oracle.HyperliquidClient")
    def test_init_creates_client(self, mock_client_class):
        """Test that client is created if not provided."""
        mock_instance = MagicMock()
        mock_client_class.return_value = mock_instance
        
        oracle = HyperliquidFundingOracle()
        assert oracle.client is mock_instance


class TestGetCurrentFundingRates:
    """Tests for fetching current funding rates."""
    
    @pytest.mark.asyncio
    async def test_get_current_funding_rates(self):
        """Test fetching current funding rates."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_meta_and_asset_contexts = AsyncMock(return_value={
            "assetCtxs": [
                {"coin": "SOL", "funding": -0.0001, "markPx": 100.0},
                {"coin": "ETH", "funding": 0.00005, "markPx": 2000.0},
            ]
        })
        
        oracle = HyperliquidFundingOracle(client=client)
        
        rates = await oracle.get_current_funding_rates()
        
        assert "SOL" in rates
        assert "ETH" in rates
        assert rates["SOL"].funding_rate == -0.0001
        assert rates["ETH"].funding_rate == 0.00005
        
        # Check annualization: -0.0001 * 3 * 365 = -0.1095
        assert rates["SOL"].annualized_rate == pytest.approx(-0.1095)
    
    @pytest.mark.asyncio
    async def test_get_current_funding_rates_empty(self):
        """Test fetching when no assets available."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_meta_and_asset_contexts = AsyncMock(return_value={
            "assetCtxs": []
        })
        
        oracle = HyperliquidFundingOracle(client=client)
        
        rates = await oracle.get_current_funding_rates()
        
        assert rates == {}


class TestGetFundingHistory:
    """Tests for funding history."""
    
    @pytest.mark.asyncio
    async def test_get_funding_history(self):
        """Test fetching funding history."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_funding_history = AsyncMock(return_value=[
            {"coin": "SOL", "fundingRate": -0.0001, "time": 1700000000000},
            {"coin": "SOL", "fundingRate": -0.00008, "time": 1700028800000},
        ])
        
        oracle = HyperliquidFundingOracle(client=client)
        
        history = await oracle.get_funding_history("SOL", hours=24)
        
        assert len(history) == 2
        assert history[0].funding_rate == -0.0001
        assert history[1].funding_rate == -0.00008
    
    @pytest.mark.asyncio
    async def test_get_funding_history_uses_cache(self):
        """Test that caching works for funding history."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_funding_history = AsyncMock(return_value=[
            {"coin": "SOL", "fundingRate": -0.0001, "time": 1700000000000},
        ])
        
        oracle = HyperliquidFundingOracle(client=client)
        
        # First call should fetch
        history1 = await oracle.get_funding_history("SOL", hours=24)
        
        # Second call should use cache
        history2 = await oracle.get_funding_history("SOL", hours=24)
        
        # Should only have fetched once
        client.get_funding_history.assert_called_once()
        assert history1 == history2
    
    @pytest.mark.asyncio
    async def test_clear_cache(self):
        """Test clearing the cache."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_funding_history = AsyncMock(return_value=[])
        
        oracle = HyperliquidFundingOracle(client=client)
        
        # Populate cache
        await oracle.get_funding_history("SOL", hours=24)
        
        # Clear cache
        oracle.clear_cache()
        
        # Should fetch again
        await oracle.get_funding_history("SOL", hours=24)
        
        assert client.get_funding_history.call_count == 2


class TestFundingRateProperties:
    """Tests for FundingRate dataclass properties."""
    
    def test_hourly_rate(self):
        """Test hourly rate calculation."""
        rate = FundingRate(
            coin="SOL",
            funding_rate=-0.0008,  # 8-hour rate
            timestamp_ms=1700000000000,
            annualized_rate=-0.0008 * 3 * 365,
        )
        
        # Hourly rate = 8-hour rate / 8
        assert rate.hourly_rate == -0.0001
    
    def test_timestamp_conversion(self):
        """Test timestamp to datetime conversion."""
        from datetime import datetime
        
        rate = FundingRate(
            coin="SOL",
            funding_rate=-0.0001,
            timestamp_ms=1700000000000,  # 2023-11-14 22:13:20 UTC
            annualized_rate=-0.1095,
        )
        
        dt = rate.timestamp
        assert isinstance(dt, datetime)
        assert dt.year == 2023


class TestPredictNextFunding:
    """Tests for funding prediction."""
    
    @pytest.mark.asyncio
    async def test_predict_next_funding(self):
        """Test funding rate prediction."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_meta_and_asset_contexts = AsyncMock(return_value={
            "assetCtxs": [
                {
                    "coin": "SOL",
                    "markPx": 101.0,  # Mark price above index
                    "oraclePx": 100.0,  # Index price
                }
            ]
        })
        
        oracle = HyperliquidFundingOracle(client=client)
        
        prediction = await oracle.predict_next_funding("SOL")
        
        assert prediction.coin == "SOL"
        # Premium = (101 - 100) / 100 = 0.01
        # Interest = 0.0001
        # Predicted = 0.01 + 0.0001 = 0.0101
        assert prediction.premium == 0.01
        assert prediction.interest_rate == 0.0001
        assert prediction.predicted_rate == pytest.approx(0.0101)
        assert prediction.confidence in ["high", "medium", "low"]
    
    @pytest.mark.asyncio
    async def test_predict_next_funding_negative_premium(self):
        """Test prediction when mark is below index."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_meta_and_asset_contexts = AsyncMock(return_value={
            "assetCtxs": [
                {
                    "coin": "SOL",
                    "markPx": 99.0,  # Mark below index
                    "oraclePx": 100.0,
                }
            ]
        })
        
        oracle = HyperliquidFundingOracle(client=client)
        
        prediction = await oracle.predict_next_funding("SOL")
        
        # Premium = (99 - 100) / 100 = -0.01
        assert prediction.premium == -0.01
        assert prediction.predicted_rate == pytest.approx(-0.0099, abs=1e-4)
    
    @pytest.mark.asyncio
    async def test_predict_next_funding_coin_not_found(self):
        """Test prediction for non-existent coin."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_meta_and_asset_contexts = AsyncMock(return_value={
            "assetCtxs": [{"coin": "BTC"}]  # No SOL
        })
        
        oracle = HyperliquidFundingOracle(client=client)
        
        with pytest.raises(ValueError, match="Coin SOL not found"):
            await oracle.predict_next_funding("SOL")


class TestCalculateFundingVolatility:
    """Tests for volatility calculation."""
    
    @pytest.mark.asyncio
    async def test_calculate_volatility(self):
        """Test volatility calculation."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_funding_history = AsyncMock(return_value=[
            {"coin": "SOL", "fundingRate": -0.0001, "time": 1700000000000},
            {"coin": "SOL", "fundingRate": -0.00012, "time": 1700028800000},
            {"coin": "SOL", "fundingRate": -0.00008, "time": 1700057600000},
        ])
        
        oracle = HyperliquidFundingOracle(client=client)
        
        volatility = await oracle.calculate_funding_volatility("SOL")
        
        # Volatility should be between 0 and 1
        assert 0 <= volatility <= 1
    
    @pytest.mark.asyncio
    async def test_calculate_volatility_insufficient_data(self):
        """Test volatility with insufficient data."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_funding_history = AsyncMock(return_value=[
            {"coin": "SOL", "fundingRate": -0.0001, "time": 1700000000000},
        ])
        
        oracle = HyperliquidFundingOracle(client=client)
        
        volatility = await oracle.calculate_funding_volatility("SOL")
        
        # Should return 0 with insufficient data
        assert volatility == 0.0
    
    @pytest.mark.asyncio
    async def test_calculate_volatility_zero_mean(self):
        """Test volatility when mean is zero."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_funding_history = AsyncMock(return_value=[
            {"coin": "SOL", "fundingRate": 0.0, "time": 1700000000000},
            {"coin": "SOL", "fundingRate": 0.0, "time": 1700028800000},
        ])
        
        oracle = HyperliquidFundingOracle(client=client)
        
        volatility = await oracle.calculate_funding_volatility("SOL")
        
        # Should handle zero mean gracefully
        assert volatility == 0.0


class TestCheckEntryCriteria:
    """Tests for entry criteria checking."""
    
    @pytest.mark.asyncio
    async def test_entry_criteria_met(self):
        """Test when all entry criteria are met."""
        oracle = HyperliquidFundingOracle()
        
        # Mock dependencies
        oracle.get_current_funding_rates = AsyncMock(return_value={
            "SOL": FundingRate("SOL", -0.0001, 1700000000000, -0.1095)
        })
        oracle.predict_next_funding = AsyncMock(return_value=FundingPrediction(
            coin="SOL",
            predicted_rate=-0.00008,
            confidence="high",
            premium=-0.00009,
            interest_rate=0.0001,
        ))
        oracle.calculate_funding_volatility = AsyncMock(return_value=0.2)  # 20%
        
        should_enter, criteria = await oracle.check_entry_criteria("SOL")
        
        assert should_enter is True
        assert criteria["current_negative"] is True
        assert criteria["predicted_negative"] is True
        assert criteria["volatility_acceptable"] is True
    
    @pytest.mark.asyncio
    async def test_entry_criteria_positive_current(self):
        """Test when current funding is positive (shorts pay)."""
        oracle = HyperliquidFundingOracle()
        
        oracle.get_current_funding_rates = AsyncMock(return_value={
            "SOL": FundingRate("SOL", 0.0001, 1700000000000, 0.1095)  # Positive
        })
        oracle.predict_next_funding = AsyncMock(return_value=FundingPrediction(
            coin="SOL",
            predicted_rate=-0.00008,
            confidence="high",
            premium=-0.00009,
            interest_rate=0.0001,
        ))
        oracle.calculate_funding_volatility = AsyncMock(return_value=0.2)
        
        should_enter, criteria = await oracle.check_entry_criteria("SOL")
        
        assert should_enter is False
        assert criteria["current_negative"] is False
    
    @pytest.mark.asyncio
    async def test_entry_criteria_high_volatility(self):
        """Test when volatility is too high."""
        oracle = HyperliquidFundingOracle()
        
        oracle.get_current_funding_rates = AsyncMock(return_value={
            "SOL": FundingRate("SOL", -0.0001, 1700000000000, -0.1095)
        })
        oracle.predict_next_funding = AsyncMock(return_value=FundingPrediction(
            coin="SOL",
            predicted_rate=-0.00008,
            confidence="high",
            premium=-0.00009,
            interest_rate=0.0001,
        ))
        oracle.calculate_funding_volatility = AsyncMock(return_value=0.6)  # 60% > 50%
        
        should_enter, criteria = await oracle.check_entry_criteria("SOL")
        
        assert should_enter is False
        assert criteria["volatility_acceptable"] is False
    
    @pytest.mark.asyncio
    async def test_entry_criteria_no_data(self):
        """Test when no funding data available."""
        oracle = HyperliquidFundingOracle()
        
        oracle.get_current_funding_rates = AsyncMock(return_value={})  # No SOL
        
        should_enter, criteria = await oracle.check_entry_criteria("SOL")
        
        assert should_enter is False
        assert "error" in criteria
