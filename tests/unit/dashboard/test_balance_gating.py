"""
Tests for balance gating logic.

These tests verify:
- Sufficient funds detection
- Insufficient funds rejection
- Edge cases (missing wallets, zero balance)
- Real USDC balance reads (native USDC contract address)
- Hyperliquid clearinghouse balance field
"""
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from backend.dashboard.api.balances import (
    BalancesResponse,
    ChainBalance,
    TokenBalance,
    USDC_CONTRACT_ARBITRUM,
    _check_sufficient_funds,
    _get_hl_clearinghouse_balance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_solana_balance(sol=1.0, usdc=100.0) -> ChainBalance:
    """Create a mock Solana chain balance."""
    return ChainBalance(
        address="So11111111111111111111111111111111111111112",
        native_balance=sol,
        native_symbol="SOL",
        tokens=[
            TokenBalance(
                token="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                symbol="USDC",
                balance=usdc,
                decimals=6,
                usd_value=usdc,
            )
        ],
    )


def _make_arbitrum_balance(eth=0.01, usdc=100.0) -> ChainBalance:
    """Create a mock Arbitrum chain balance."""
    return ChainBalance(
        address="0x" + "a" * 40,
        native_balance=eth,
        native_symbol="ETH",
        tokens=[
            TokenBalance(
                token=USDC_CONTRACT_ARBITRUM,
                symbol="USDC",
                balance=usdc,
                decimals=6,
                usd_value=usdc,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheckSufficientFunds:
    """Tests for the _check_sufficient_funds function.

    The function checks Solana (SOL gas + USDC) and Hyperliquid clearinghouse balance.
    Arbitrum is NOT checked — it's only a pass-through for deposits to HL.
    """

    def test_sufficient_funds(self):
        """Test that sufficient balances return True."""
        sol = _make_solana_balance(sol=1.0, usdc=500.0)
        has_funds, reason = _check_sufficient_funds(sol, 500.0)
        assert has_funds is True
        assert reason == ""

    def test_no_solana_wallet(self):
        """Test that missing Solana wallet returns False."""
        has_funds, reason = _check_sufficient_funds(None, 500.0)
        assert has_funds is False
        assert "Solana" in reason

    def test_insufficient_sol_for_gas(self):
        """Test rejection when SOL balance is too low for gas."""
        sol = _make_solana_balance(sol=0.01, usdc=500.0)
        has_funds, reason = _check_sufficient_funds(sol, 500.0)
        assert has_funds is False
        assert "SOL" in reason

    def test_insufficient_usdc_solana(self):
        """Test rejection when USDC on Solana is too low."""
        sol = _make_solana_balance(sol=1.0, usdc=5.0)
        has_funds, reason = _check_sufficient_funds(sol, 500.0)
        assert has_funds is False
        assert "USDC on Solana" in reason

    def test_insufficient_hl_balance(self):
        """Test rejection when Hyperliquid clearinghouse USDC is too low."""
        sol = _make_solana_balance(sol=1.0, usdc=100.0)
        has_funds, reason = _check_sufficient_funds(sol, 5.0)
        assert has_funds is False
        assert "Hyperliquid" in reason

    def test_hl_balance_none(self):
        """Test rejection when HL balance is None (not available)."""
        sol = _make_solana_balance(sol=1.0, usdc=100.0)
        has_funds, reason = _check_sufficient_funds(sol, None)
        assert has_funds is False
        assert "Hyperliquid" in reason

    def test_missing_evm_wallet_means_no_hl(self):
        """Test that a missing EVM wallet results in HL balance None.

        Without an EVM address the backend can't fetch the HL clearinghouse
        balance, so hl_clearinghouse will be None — which fails the check.
        Users need an Arbitrum wallet to deposit USDC and bridge to HL.
        """
        sol = _make_solana_balance(sol=1.0, usdc=100.0)
        # No EVM wallet → hl_clearinghouse is None
        has_funds, reason = _check_sufficient_funds(sol, None)
        assert has_funds is False
        assert "Hyperliquid" in reason

    def test_zero_sol_balance(self):
        """Test rejection with zero SOL."""
        sol = _make_solana_balance(sol=0.0, usdc=500.0)
        has_funds, reason = _check_sufficient_funds(sol, 500.0)
        assert has_funds is False

    def test_zero_usdc_both(self):
        """Test rejection with zero USDC on Solana and HL."""
        sol = _make_solana_balance(sol=1.0, usdc=0.0)
        has_funds, reason = _check_sufficient_funds(sol, 0.0)
        assert has_funds is False

    def test_exactly_minimum_sol(self):
        """Test that exactly minimum SOL passes."""
        sol = _make_solana_balance(sol=0.05, usdc=100.0)
        has_funds, reason = _check_sufficient_funds(sol, 100.0)
        assert has_funds is True

    def test_exactly_minimum_usdc(self):
        """Test that exactly minimum USDC passes on both Solana and HL."""
        sol = _make_solana_balance(sol=1.0, usdc=10.0)
        has_funds, reason = _check_sufficient_funds(sol, 10.0)
        assert has_funds is True


class TestUsdcContractAddress:
    """Tests for native USDC contract address."""

    def test_native_usdc_address(self):
        """Verify native USDC address (not bridged USDC.e)."""
        assert USDC_CONTRACT_ARBITRUM == "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
        assert USDC_CONTRACT_ARBITRUM != "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8"


class TestBalancesResponseModel:
    """Tests for BalancesResponse model with HL clearinghouse field."""

    def test_response_includes_hl_clearinghouse(self):
        """Test that BalancesResponse has hyperliquid_clearinghouse field."""
        response = BalancesResponse(
            hyperliquid_clearinghouse=5000.0,
            has_sufficient_funds=True,
        )
        assert response.hyperliquid_clearinghouse == 5000.0

    def test_response_hl_clearinghouse_default_none(self):
        """Test that hyperliquid_clearinghouse defaults to None."""
        response = BalancesResponse()
        assert response.hyperliquid_clearinghouse is None


class TestHlClearinghouseBalance:
    """Tests for HL clearinghouse balance API helper."""

    @pytest.mark.asyncio
    async def test_get_hl_clearinghouse_balance_success(self):
        """Test fetching HL clearinghouse balance."""
        with patch("backend.dashboard.api.balances.HyperliquidTrader") as mock_trader_cls:
            mock_trader = MagicMock()
            mock_trader.get_deposited_balance = AsyncMock(return_value=1234.56)
            mock_trader_cls.return_value = mock_trader

            balance = await _get_hl_clearinghouse_balance("0xWallet")

            assert balance == 1234.56
            mock_trader_cls.assert_called_once_with(wallet_address="0xWallet")

    @pytest.mark.asyncio
    async def test_get_hl_clearinghouse_balance_zero(self):
        """Test zero HL balance returns 0."""
        with patch("backend.dashboard.api.balances.HyperliquidTrader") as mock_trader_cls:
            mock_trader = MagicMock()
            mock_trader.get_deposited_balance = AsyncMock(return_value=0)
            mock_trader_cls.return_value = mock_trader

            balance = await _get_hl_clearinghouse_balance("0xWallet")

            assert balance == 0.0

    @pytest.mark.asyncio
    async def test_get_hl_clearinghouse_balance_error(self):
        """Test error returns None."""
        with patch("backend.dashboard.api.balances.HyperliquidTrader") as mock_trader_cls:
            mock_trader_cls.side_effect = Exception("API error")

            balance = await _get_hl_clearinghouse_balance("0xWallet")

            assert balance is None
