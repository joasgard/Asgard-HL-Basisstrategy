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
    """Tests for the _check_sufficient_funds function."""

    def test_sufficient_funds(self):
        """Test that sufficient balances return True."""
        sol = _make_solana_balance(sol=1.0, usdc=500.0)
        arb = _make_arbitrum_balance(eth=0.01, usdc=500.0)
        has_funds, reason = _check_sufficient_funds(sol, arb)
        assert has_funds is True
        assert reason == ""

    def test_no_wallets(self):
        """Test that missing wallets return False."""
        has_funds, reason = _check_sufficient_funds(None, None)
        assert has_funds is False
        assert "No wallet" in reason

    def test_insufficient_sol_for_gas(self):
        """Test rejection when SOL balance is too low for gas."""
        sol = _make_solana_balance(sol=0.01, usdc=500.0)
        arb = _make_arbitrum_balance()
        has_funds, reason = _check_sufficient_funds(sol, arb)
        assert has_funds is False
        assert "SOL" in reason

    def test_insufficient_usdc_solana(self):
        """Test rejection when USDC on Solana is too low."""
        sol = _make_solana_balance(sol=1.0, usdc=5.0)
        arb = _make_arbitrum_balance()
        has_funds, reason = _check_sufficient_funds(sol, arb)
        assert has_funds is False
        assert "USDC on Solana" in reason

    def test_insufficient_usdc_arbitrum(self):
        """Test rejection when USDC on Arbitrum is too low."""
        sol = _make_solana_balance(sol=1.0, usdc=100.0)
        arb = _make_arbitrum_balance(eth=0.01, usdc=5.0)
        has_funds, reason = _check_sufficient_funds(sol, arb)
        assert has_funds is False
        assert "USDC on Arbitrum" in reason

    def test_missing_solana_wallet(self):
        """Test rejection when Solana wallet is not configured."""
        arb = _make_arbitrum_balance()
        has_funds, reason = _check_sufficient_funds(None, arb)
        assert has_funds is False
        assert "Solana wallet" in reason

    def test_missing_arbitrum_wallet(self):
        """Test rejection when Arbitrum wallet is not configured."""
        sol = _make_solana_balance()
        has_funds, reason = _check_sufficient_funds(sol, None)
        assert has_funds is False
        assert "Arbitrum wallet" in reason

    def test_zero_sol_balance(self):
        """Test rejection with zero SOL."""
        sol = _make_solana_balance(sol=0.0, usdc=500.0)
        arb = _make_arbitrum_balance()
        has_funds, reason = _check_sufficient_funds(sol, arb)
        assert has_funds is False

    def test_zero_usdc_both_chains(self):
        """Test rejection with zero USDC on both chains."""
        sol = _make_solana_balance(sol=1.0, usdc=0.0)
        arb = _make_arbitrum_balance(eth=0.01, usdc=0.0)
        has_funds, reason = _check_sufficient_funds(sol, arb)
        assert has_funds is False

    def test_exactly_minimum_sol(self):
        """Test that exactly minimum SOL passes."""
        sol = _make_solana_balance(sol=0.05, usdc=100.0)
        arb = _make_arbitrum_balance()
        has_funds, reason = _check_sufficient_funds(sol, arb)
        assert has_funds is True

    def test_exactly_minimum_usdc(self):
        """Test that exactly minimum USDC passes."""
        sol = _make_solana_balance(sol=1.0, usdc=10.0)
        arb = _make_arbitrum_balance(eth=0.01, usdc=10.0)
        has_funds, reason = _check_sufficient_funds(sol, arb)
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
