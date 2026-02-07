"""
Tests for dashboard rates API.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi import HTTPException


class TestGetRates:
    """Tests for GET /rates endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_get_rates_success(self, mock_oracle_class, mock_asgard_class):
        """Test fetching rates successfully from both venues."""
        from src.dashboard.api.rates import get_rates
        
        # Mock Asgard client
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_asgard.get_markets.return_value = {
            "strategies": {
                "SOL": {
                    "liquiditySources": [
                        {
                            "lendingProtocol": 1,  # kamino
                            "tokenALendingApyRate": 0.05,
                            "tokenBBorrowingApyRate": 0.08
                        },
                        {
                            "lendingProtocol": 2,  # solend
                            "tokenALendingApyRate": 0.04,
                            "tokenBBorrowingApyRate": 0.09
                        }
                    ]
                },
                "jitoSOL": {
                    "liquiditySources": [
                        {
                            "lendingProtocol": 1,  # kamino
                            "tokenALendingApyRate": 0.06,
                            "tokenBBorrowingApyRate": 0.08
                        }
                    ]
                }
            }
        }
        
        # Mock Hyperliquid oracle
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_rate = MagicMock()
        mock_rate.funding_rate = -0.0001
        mock_rate.annualized_rate = -0.1095  # -0.0001 * 3 * 365
        
        mock_oracle.get_current_funding_rates.return_value = {"SOL": mock_rate}
        
        result = await get_rates(leverage=3.0)
        
        assert "asgard" in result
        assert "hyperliquid" in result
        assert result["leverage"] == 3.0
        
        # Check Asgard rates
        assert "sol" in result["asgard"]
        assert "jitosol" in result["asgard"]
        
        # Check Hyperliquid rates
        assert result["hyperliquid"]["funding_rate"] != 0
        assert result["hyperliquid"]["annualized"] != 0
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_get_rates_with_leverage(self, mock_oracle_class, mock_asgard_class):
        """Test fetching rates with different leverage values."""
        from src.dashboard.api.rates import get_rates
        
        # Mock Asgard client
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard_class.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_asgard.get_markets.return_value = {"strategies": {}}
        
        # Mock Hyperliquid oracle
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_rate = MagicMock()
        mock_rate.funding_rate = -0.0001
        mock_rate.annualized_rate = -0.1095
        mock_oracle.get_current_funding_rates.return_value = {"SOL": mock_rate}
        
        # Test with leverage 2.0
        result = await get_rates(leverage=2.0)
        assert result["leverage"] == 2.0
        
        # Test with leverage 4.0
        result = await get_rates(leverage=4.0)
        assert result["leverage"] == 4.0
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_get_rates_asgard_error(self, mock_oracle_class, mock_asgard_class):
        """Test handling Asgard API errors gracefully."""
        from src.dashboard.api.rates import get_rates
        
        # Mock Asgard client to raise exception
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard_class.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_asgard.get_markets.side_effect = Exception("Asgard API error")
        
        # Mock Hyperliquid oracle
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_rate = MagicMock()
        mock_rate.funding_rate = -0.0001
        mock_rate.annualized_rate = -0.1095
        mock_oracle.get_current_funding_rates.return_value = {"SOL": mock_rate}
        
        result = await get_rates(leverage=3.0)
        
        # Should still return data, but Asgard rates empty
        assert "asgard" in result
        assert "hyperliquid" in result
        assert result["asgard"]["sol"] == {}
        assert result["asgard"]["jitosol"] == {}
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_get_rates_hyperliquid_error(self, mock_oracle_class, mock_asgard_class):
        """Test handling Hyperliquid API errors gracefully."""
        from src.dashboard.api.rates import get_rates
        
        # Mock Asgard client
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard_class.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_asgard.get_markets.return_value = {"strategies": {}}
        
        # Mock Hyperliquid oracle to raise exception
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle_class.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_oracle.get_current_funding_rates.side_effect = Exception("HL API error")
        
        result = await get_rates(leverage=3.0)
        
        # Should still return data, but Hyperliquid rates zeroed
        assert result["hyperliquid"]["funding_rate"] == 0.0
        assert result["hyperliquid"]["predicted"] == 0.0
        assert result["hyperliquid"]["annualized"] == 0.0
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_get_rates_sol_not_found(self, mock_oracle_class, mock_asgard_class):
        """Test when SOL rate is not found in Hyperliquid response."""
        from src.dashboard.api.rates import get_rates
        
        # Mock Asgard client
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard_class.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_asgard.get_markets.return_value = {"strategies": {}}
        
        # Mock Hyperliquid oracle - no SOL in response
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle_class.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_oracle.get_current_funding_rates.return_value = {"BTC": MagicMock()}
        
        result = await get_rates(leverage=3.0)
        
        # Should return zeroed rates
        assert result["hyperliquid"]["funding_rate"] == 0.0
        assert result["hyperliquid"]["predicted"] == 0.0
        assert result["hyperliquid"]["annualized"] == 0.0


class TestFetchAsgardRates:
    """Tests for _fetch_asgard_rates internal function."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    async def test_fetch_asgard_rates_calculation(self, mock_asgard_class):
        """Test APY calculation for LSTs with leverage."""
        from src.dashboard.api.rates import _fetch_asgard_rates
        
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        # jitoSOL: staking_apy=0.08 (8%), lending_apy=0.06, borrowing_apy=0.08
        # Net APY at 3x leverage = (0.06 + 0.08 - 0.08 * 2) * 100 = -2.0%
        mock_asgard.get_markets.return_value = {
            "strategies": {
                "jitoSOL": {
                    "liquiditySources": [
                        {
                            "lendingProtocol": 1,  # kamino
                            "tokenALendingApyRate": 0.06,
                            "tokenBBorrowingApyRate": 0.08
                        }
                    ]
                }
            }
        }
        
        result = await _fetch_asgard_rates(leverage=3.0)
        
        assert "jitosol" in result
        assert "kamino" in result["jitosol"]
        # (0.06 + 0.08 - 0.08 * 2) * 100 = -2.0
        assert result["jitosol"]["kamino"] == -2.0
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    async def test_fetch_asgard_rates_sol_no_staking(self, mock_asgard_class):
        """Test SOL rates without staking yield (native SOL)."""
        from src.dashboard.api.rates import _fetch_asgard_rates
        
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        # SOL: staking_apy=0, lending_apy=0.05, borrowing_apy=0.08
        # Net APY at 3x leverage = (0.05 + 0 - 0.08 * 2) * 100 = -11.0%
        mock_asgard.get_markets.return_value = {
            "strategies": {
                "SOL": {
                    "liquiditySources": [
                        {
                            "lendingProtocol": 1,  # kamino
                            "tokenALendingApyRate": 0.05,
                            "tokenBBorrowingApyRate": 0.08
                        }
                    ]
                }
            }
        }
        
        result = await _fetch_asgard_rates(leverage=3.0)
        
        assert "sol" in result
        assert "kamino" in result["sol"]
        # (0.05 + 0 - 0.08 * 2) * 100 = -11.0
        assert result["sol"]["kamino"] == -11.0
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    async def test_fetch_asgard_rates_unknown_protocol(self, mock_asgard_class):
        """Test handling unknown protocol IDs gracefully."""
        from src.dashboard.api.rates import _fetch_asgard_rates
        
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_asgard.get_markets.return_value = {
            "strategies": {
                "SOL": {
                    "liquiditySources": [
                        {
                            "lendingProtocol": 99,  # Unknown protocol
                            "tokenALendingApyRate": 0.05,
                            "tokenBBorrowingApyRate": 0.08
                        },
                        {
                            "lendingProtocol": 1,  # kamino
                            "tokenALendingApyRate": 0.06,
                            "tokenBBorrowingApyRate": 0.08
                        }
                    ]
                }
            }
        }
        
        result = await _fetch_asgard_rates(leverage=3.0)
        
        # Unknown protocol should be skipped, known should be present
        assert "sol" in result
        assert "kamino" in result["sol"]
        assert len(result["sol"]) == 1  # Only kamino
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    async def test_fetch_asgard_rates_empty_strategies(self, mock_asgard_class):
        """Test handling empty strategies response."""
        from src.dashboard.api.rates import _fetch_asgard_rates
        
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_asgard.get_markets.return_value = {"strategies": {}}
        
        result = await _fetch_asgard_rates(leverage=3.0)
        
        # Should return empty dicts for all assets
        assert result["sol"] == {}
        assert result["jitosol"] == {}
        assert result["jupsol"] == {}
        assert result["inf"] == {}


class TestFetchHyperliquidRates:
    """Tests for _fetch_hyperliquid_rates internal function."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_fetch_hyperliquid_rates_success(self, mock_oracle_class):
        """Test fetching Hyperliquid rates successfully."""
        from src.dashboard.api.rates import _fetch_hyperliquid_rates
        
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_rate = MagicMock()
        mock_rate.funding_rate = -0.0001  # -0.01% per 8 hours
        mock_rate.annualized_rate = -0.1095  # -10.95% annualized
        
        mock_oracle.get_current_funding_rates.return_value = {"SOL": mock_rate}
        
        result = await _fetch_hyperliquid_rates(leverage=3.0)
        
        # funding_rate scaled by leverage: -0.0001 * 3 * 100 = -0.03%
        assert result["funding_rate"] == pytest.approx(-0.03, abs=0.01)
        # annualized scaled by leverage: -0.1095 * 3 * 100 = -32.85%
        assert result["annualized"] == pytest.approx(-32.85, abs=0.1)
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_fetch_hyperliquid_rates_positive_funding(self, mock_oracle_class):
        """Test positive funding rates (shorts pay longs)."""
        from src.dashboard.api.rates import _fetch_hyperliquid_rates
        
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_rate = MagicMock()
        mock_rate.funding_rate = 0.0001  # +0.01% per 8 hours (shorts pay)
        mock_rate.annualized_rate = 0.1095
        
        mock_oracle.get_current_funding_rates.return_value = {"SOL": mock_rate}
        
        result = await _fetch_hyperliquid_rates(leverage=3.0)
        
        # Positive funding means shorting costs money
        assert result["funding_rate"] > 0
        assert result["annualized"] > 0
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_fetch_hyperliquid_rates_exception(self, mock_oracle_class):
        """Test handling exceptions gracefully."""
        from src.dashboard.api.rates import _fetch_hyperliquid_rates
        
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle_class.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_oracle.get_current_funding_rates.side_effect = Exception("API error")
        
        result = await _fetch_hyperliquid_rates(leverage=3.0)
        
        # Should return zeroed values
        assert result["funding_rate"] == 0.0
        assert result["predicted"] == 0.0
        assert result["annualized"] == 0.0


class TestGetSimpleRates:
    """Tests for GET /rates/simple endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.get_rates')
    async def test_get_simple_rates(self, mock_get_rates):
        """Test simplified rates endpoint uses default leverage."""
        from src.dashboard.api.rates import get_simple_rates
        
        mock_get_rates.return_value = {
            "asgard": {"sol": {"kamino": 10.0}},
            "hyperliquid": {"funding_rate": -0.03},
            "leverage": 3.0
        }
        
        result = await get_simple_rates()
        
        mock_get_rates.assert_called_once_with(leverage=3.0)
        assert result["leverage"] == 3.0


class TestLeverageValidation:
    """Tests for leverage query parameter validation - verified via model."""
    
    def test_leverage_bounds_validation(self):
        """Test leverage bounds are validated by the model."""
        # The endpoint uses: leverage: float = Query(3.0, ge=2.0, le=4.0, ...)
        # FastAPI will validate these bounds automatically
        # Test via the OpenPositionRequest model which has same constraints
        from src.dashboard.api.positions import OpenPositionRequest
        from pydantic import ValidationError
        import pytest
        
        # Valid values
        req = OpenPositionRequest(asset="SOL", leverage=2.0, size_usd=10000)
        assert req.leverage == 2.0
        
        req = OpenPositionRequest(asset="SOL", leverage=4.0, size_usd=10000)
        assert req.leverage == 4.0
        
        # Invalid - too low (would be rejected by FastAPI Query)
        with pytest.raises(ValidationError):
            OpenPositionRequest(asset="SOL", leverage=1.5, size_usd=10000)
        
        # Invalid - too high (would be rejected by FastAPI Query)
        with pytest.raises(ValidationError):
            OpenPositionRequest(asset="SOL", leverage=4.5, size_usd=10000)
