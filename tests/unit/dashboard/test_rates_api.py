"""Tests for dashboard rates API."""
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
        mock_asgard_class.return_value = mock_asgard
        mock_asgard.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard.__aexit__ = AsyncMock(return_value=False)
        
        mock_asgard.get_markets = AsyncMock(return_value={
            "strategies": {
                "SOL/USDC": {
                    "liquiditySources": [
                        {
                            "lendingProtocol": 1,  # kamino
                            "tokenALendingApyRate": 0.05,
                            "tokenBBorrowingApyRate": 0.08
                        },
                        {
                            "lendingProtocol": 3,  # drift
                            "tokenALendingApyRate": 0.12,
                            "tokenBBorrowingApyRate": 0.035
                        }
                    ]
                }
            }
        })
        
        # Mock Hyperliquid oracle
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value = mock_oracle
        mock_oracle.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle.__aexit__ = AsyncMock(return_value=False)
        
        mock_rate = MagicMock()
        mock_rate.funding_rate = -0.0001
        mock_rate.annualized_rate = -0.1095
        
        mock_oracle.get_current_funding_rates = AsyncMock(return_value={"SOL": mock_rate})
        
        result = await get_rates(leverage=3.0)
        
        assert "asgard" in result
        assert "hyperliquid" in result
        assert "combined" in result
        assert result["leverage"] == 3.0
        
        # Check Asgard rates (flat structure now)
        assert "kamino" in result["asgard"]
        assert "drift" in result["asgard"]
        # (0.05 * 3 - 0.08 * 2) * 100 = (0.15 - 0.16) * 100 = -1.0
        assert result["asgard"]["kamino"] == -1.0
        # (0.12 * 3 - 0.035 * 2) * 100 = (0.36 - 0.07) * 100 = +29.0
        assert result["asgard"]["drift"] == 29.0
        
        # Check Hyperliquid rates
        assert result["hyperliquid"]["funding_rate"] != 0
        assert result["hyperliquid"]["annualized"] != 0
        
        # Check combined rates
        assert "kamino" in result["combined"]
        assert "drift" in result["combined"]
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_get_rates_with_leverage(self, mock_oracle_class, mock_asgard_class):
        """Test fetching rates with different leverage values."""
        from src.dashboard.api.rates import get_rates
        
        # Mock Asgard client
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value = mock_asgard
        mock_asgard.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard.__aexit__ = AsyncMock(return_value=False)
        
        mock_asgard.get_markets = AsyncMock(return_value={
            "strategies": {
                "SOL/USDC": {
                    "liquiditySources": [
                        {
                            "lendingProtocol": 1,
                            "tokenALendingApyRate": 0.05,
                            "tokenBBorrowingApyRate": 0.08
                        }
                    ]
                }
            }
        })
        
        # Mock Hyperliquid oracle
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value = mock_oracle
        mock_oracle.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle.__aexit__ = AsyncMock(return_value=False)
        
        mock_rate = MagicMock()
        mock_rate.funding_rate = -0.0001
        mock_rate.annualized_rate = -0.1095
        mock_oracle.get_current_funding_rates = AsyncMock(return_value={"SOL": mock_rate})
        
        # Test with leverage 2.0
        result = await get_rates(leverage=2.0)
        assert result["leverage"] == 2.0
        # At 2x: (0.05 * 2 - 0.08 * 1) * 100 = (0.10 - 0.08) * 100 = +2.0
        assert result["asgard"]["kamino"] == 2.0
        
        # Test with leverage 4.0
        result = await get_rates(leverage=4.0)
        assert result["leverage"] == 4.0
        # At 4x: (0.05 * 4 - 0.08 * 3) * 100 = (0.20 - 0.24) * 100 = -4.0
        assert result["asgard"]["kamino"] == -4.0
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_get_rates_asgard_error(self, mock_oracle_class, mock_asgard_class):
        """Test handling Asgard API errors gracefully."""
        from src.dashboard.api.rates import get_rates
        
        # Mock Asgard client to raise exception
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value = mock_asgard
        mock_asgard.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard.__aexit__ = AsyncMock(return_value=False)
        mock_asgard.get_markets = AsyncMock(side_effect=Exception("Asgard API error"))
        
        # Mock Hyperliquid oracle
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value = mock_oracle
        mock_oracle.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle.__aexit__ = AsyncMock(return_value=False)
        
        mock_rate = MagicMock()
        mock_rate.funding_rate = -0.0001
        mock_rate.annualized_rate = -0.1095
        mock_oracle.get_current_funding_rates = AsyncMock(return_value={"SOL": mock_rate})
        
        result = await get_rates(leverage=3.0)
        
        # Should still return data, but Asgard rates empty
        assert "asgard" in result
        assert "hyperliquid" in result
        assert result["asgard"] == {}
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_get_rates_hyperliquid_error(self, mock_oracle_class, mock_asgard_class):
        """Test handling Hyperliquid API errors gracefully."""
        from src.dashboard.api.rates import get_rates
        
        # Mock Asgard client
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value = mock_asgard
        mock_asgard.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard.__aexit__ = AsyncMock(return_value=False)
        mock_asgard.get_markets = AsyncMock(return_value={
            "strategies": {
                "SOL/USDC": {
                    "liquiditySources": [
                        {
                            "lendingProtocol": 1,
                            "tokenALendingApyRate": 0.05,
                            "tokenBBorrowingApyRate": 0.08
                        }
                    ]
                }
            }
        })
        
        # Mock Hyperliquid oracle to raise exception
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value = mock_oracle
        mock_oracle.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle.__aexit__ = AsyncMock(return_value=False)
        mock_oracle.get_current_funding_rates = AsyncMock(side_effect=Exception("HL API error"))
        
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
        mock_asgard_class.return_value = mock_asgard
        mock_asgard.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard.__aexit__ = AsyncMock(return_value=False)
        mock_asgard.get_markets = AsyncMock(return_value={"strategies": {}})
        
        # Mock Hyperliquid oracle - no SOL in response
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value = mock_oracle
        mock_oracle.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle.__aexit__ = AsyncMock(return_value=False)
        mock_oracle.get_current_funding_rates = AsyncMock(return_value={"BTC": MagicMock()})
        
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
        """Test APY calculation at specified leverage."""
        from src.dashboard.api.rates import _fetch_asgard_rates
        
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value = mock_asgard
        mock_asgard.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard.__aexit__ = AsyncMock(return_value=False)
        
        # SOL: lending_apy=0.12, borrowing_apy=0.035
        # Net APY at 3x leverage = (0.12 * 3 - 0.035 * 2) * 100 = +29.0%
        # = (0.36 - 0.07) * 100 = 29.0
        mock_asgard.get_markets = AsyncMock(return_value={
            "strategies": {
                "SOL/USDC": {
                    "liquiditySources": [
                        {
                            "lendingProtocol": 3,  # drift
                            "tokenALendingApyRate": 0.12,
                            "tokenBBorrowingApyRate": 0.035
                        }
                    ]
                }
            }
        })
        
        result = await _fetch_asgard_rates(leverage=3.0)
        
        assert "drift" in result
        # (0.12 * 3 - 0.035 * 2) * 100 = 29.0
        assert result["drift"] == 29.0
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    async def test_fetch_asgard_rates_unknown_protocol(self, mock_asgard_class):
        """Test handling unknown protocol IDs gracefully."""
        from src.dashboard.api.rates import _fetch_asgard_rates
        
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value = mock_asgard
        mock_asgard.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard.__aexit__ = AsyncMock(return_value=False)
        
        mock_asgard.get_markets = AsyncMock(return_value={
            "strategies": {
                "SOL/USDC": {
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
        })
        
        result = await _fetch_asgard_rates(leverage=3.0)
        
        # Unknown protocol should be skipped, known should be present
        assert "kamino" in result
        assert len(result) == 1  # Only kamino
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    async def test_fetch_asgard_rates_empty_strategies(self, mock_asgard_class):
        """Test handling empty strategies response."""
        from src.dashboard.api.rates import _fetch_asgard_rates
        
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value = mock_asgard
        mock_asgard.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard.__aexit__ = AsyncMock(return_value=False)
        
        mock_asgard.get_markets = AsyncMock(return_value={"strategies": {}})
        
        result = await _fetch_asgard_rates(leverage=3.0)
        
        # Should return empty dict
        assert result == {}
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.AsgardClient')
    async def test_fetch_asgard_rates_missing_sol_usdc(self, mock_asgard_class):
        """Test when SOL/USDC strategy is missing."""
        from src.dashboard.api.rates import _fetch_asgard_rates
        
        mock_asgard = AsyncMock()
        mock_asgard_class.return_value = mock_asgard
        mock_asgard.__aenter__ = AsyncMock(return_value=mock_asgard)
        mock_asgard.__aexit__ = AsyncMock(return_value=False)
        
        # Only other strategies present
        mock_asgard.get_markets = AsyncMock(return_value={
            "strategies": {
                "JITOSOL/USDC": {"liquiditySources": []},
                "BTC/USDC": {"liquiditySources": []}
            }
        })
        
        result = await _fetch_asgard_rates(leverage=3.0)
        
        # Should return empty dict since SOL/USDC not found
        assert result == {}


class TestFetchHyperliquidRates:
    """Tests for _fetch_hyperliquid_rates internal function."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_fetch_hyperliquid_rates_success(self, mock_oracle_class):
        """Test fetching Hyperliquid rates successfully."""
        from src.dashboard.api.rates import _fetch_hyperliquid_rates
        
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value = mock_oracle
        mock_oracle.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle.__aexit__ = AsyncMock(return_value=False)
        
        mock_rate = MagicMock()
        mock_rate.funding_rate = -0.000007  # Hourly rate: -0.0007%
        mock_rate.annualized_rate = -0.06132  # Annualized: -6.13% (hourly * 24 * 365)
        
        mock_oracle.get_current_funding_rates = AsyncMock(return_value={"SOL": mock_rate})
        
        result = await _fetch_hyperliquid_rates(leverage=3.0)
        
        # Hourly funding rate %: -0.000007 * 100 = -0.0007%
        assert result["funding_rate"] == pytest.approx(-0.0007, abs=0.0001)
        # Annualized at 3x leverage: -6.13% * 3 = -18.39%
        assert result["annualized"] == pytest.approx(-18.39, abs=0.5)
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_fetch_hyperliquid_rates_sol_not_found(self, mock_oracle_class):
        """Test when SOL is not in the funding rates response."""
        from src.dashboard.api.rates import _fetch_hyperliquid_rates
        
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value = mock_oracle
        mock_oracle.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle.__aexit__ = AsyncMock(return_value=False)
        
        # Only BTC in response
        mock_rate = MagicMock()
        mock_oracle.get_current_funding_rates = AsyncMock(return_value={"BTC": mock_rate})
        
        result = await _fetch_hyperliquid_rates(leverage=3.0)
        
        assert result["funding_rate"] == 0.0
        assert result["predicted"] == 0.0
        assert result["annualized"] == 0.0
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.rates.HyperliquidFundingOracle')
    async def test_fetch_hyperliquid_rates_api_error(self, mock_oracle_class):
        """Test handling API errors gracefully."""
        from src.dashboard.api.rates import _fetch_hyperliquid_rates
        
        mock_oracle = AsyncMock()
        mock_oracle_class.return_value = mock_oracle
        mock_oracle.__aenter__ = AsyncMock(return_value=mock_oracle)
        mock_oracle.__aexit__ = AsyncMock(return_value=False)
        mock_oracle.get_current_funding_rates = AsyncMock(side_effect=Exception("API Error"))
        
        result = await _fetch_hyperliquid_rates(leverage=3.0)
        
        assert result["funding_rate"] == 0.0
        assert result["predicted"] == 0.0
        assert result["annualized"] == 0.0
