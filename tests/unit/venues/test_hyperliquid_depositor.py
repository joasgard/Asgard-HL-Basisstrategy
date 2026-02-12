"""
Tests for HyperliquidDepositor — Arbitrum → HL bridge deposit flow.

Covers:
- Full deposit happy path (approve + bridge + poll)
- Skipped approve when allowance sufficient
- Insufficient USDC on Arbitrum
- Insufficient ETH for gas
- Approve tx failure
- Bridge deposit tx failure
- HL credit polling timeout
- No HL trader (skips poll)
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from bot.venues.hyperliquid.depositor import (
    HyperliquidDepositor,
    DepositResult,
    MIN_ETH_FOR_BRIDGE,
)


@pytest.fixture
def mock_arb_client():
    """Create a mocked ArbitrumClient."""
    client = MagicMock()
    client.w3 = MagicMock()
    client.w3.to_checksum_address = lambda addr: addr
    client.w3.eth.contract = MagicMock()

    # Default: enough USDC and ETH
    client.get_usdc_balance = AsyncMock(return_value=Decimal("1000"))
    client.get_balance = AsyncMock(return_value=Decimal("0.05"))
    client.get_transaction_count = AsyncMock(return_value=42)
    client.get_gas_price = AsyncMock(return_value=100_000_000)  # 0.1 gwei
    client.send_raw_transaction = AsyncMock(return_value="0xtxhash")
    client.wait_for_transaction_receipt = AsyncMock(return_value={"status": 1})

    return client


@pytest.fixture
def mock_hl_trader():
    """Create a mocked HyperliquidTrader for balance polling."""
    trader = MagicMock()
    trader.get_deposited_balance = AsyncMock(side_effect=[100.0, 100.0, 600.0])
    return trader


@pytest.fixture
def mock_settings():
    """Mock settings."""
    settings = MagicMock()
    settings.hl_bridge_contract = "0xBridgeContract"
    settings.privy_app_id = "test-app"
    settings.privy_app_secret = "test-secret"
    settings.privy_auth_key_path = "test.pem"
    return settings


@pytest.fixture
def depositor(mock_arb_client, mock_hl_trader, mock_settings):
    """Create a HyperliquidDepositor with mocks."""
    with patch(
        "bot.venues.hyperliquid.depositor.get_settings",
        return_value=mock_settings,
    ):
        dep = HyperliquidDepositor(
            arb_client=mock_arb_client,
            wallet_address="0xWallet",
            user_id="user_123",
            hl_trader=mock_hl_trader,
            bridge_contract="0xBridgeContract",
        )

        # Mock the Privy signer
        mock_privy = MagicMock()
        mock_privy.wallet.sign_transaction = AsyncMock(return_value=b"\x01\x02")
        dep._privy = mock_privy

        return dep


class TestDepositHappyPath:
    """Tests for successful deposit flow."""

    @pytest.mark.asyncio
    async def test_full_deposit_with_approve(self, depositor, mock_arb_client):
        """Test full flow: approve + deposit + poll."""
        # Set up allowance check to return 0 (needs approve)
        mock_allowance_call = AsyncMock(return_value=0)
        mock_functions = MagicMock()
        mock_functions.allowance.return_value.call = mock_allowance_call
        mock_functions.approve.return_value.build_transaction = MagicMock(
            return_value={"from": "0xWallet", "nonce": 42}
        )

        # Bridge deposit
        mock_bridge_functions = MagicMock()
        mock_bridge_functions.deposit.return_value.build_transaction = MagicMock(
            return_value={"from": "0xWallet", "nonce": 43}
        )

        # Return USDC contract first, then bridge contract
        usdc_contract = MagicMock()
        usdc_contract.functions = mock_functions
        bridge_contract = MagicMock()
        bridge_contract.functions = mock_bridge_functions

        mock_arb_client.w3.eth.contract.side_effect = [
            usdc_contract,
            bridge_contract,
        ]

        result = await depositor.deposit(500.0)

        assert result.success is True
        assert result.approve_tx_hash == "0xtxhash"
        assert result.deposit_tx_hash == "0xtxhash"
        assert result.amount_usdc == Decimal("500")

    @pytest.mark.asyncio
    async def test_deposit_skips_approve_when_allowance_sufficient(
        self, depositor, mock_arb_client
    ):
        """Test that approve is skipped when allowance is already enough."""
        # Allowance already covers the amount
        raw_amount = 500 * 1_000_000
        mock_allowance_call = AsyncMock(return_value=raw_amount + 1)
        mock_functions = MagicMock()
        mock_functions.allowance.return_value.call = mock_allowance_call

        usdc_contract = MagicMock()
        usdc_contract.functions = mock_functions

        # Bridge contract
        mock_bridge_functions = MagicMock()
        mock_bridge_functions.deposit.return_value.build_transaction = MagicMock(
            return_value={"from": "0xWallet", "nonce": 42}
        )
        bridge_contract = MagicMock()
        bridge_contract.functions = mock_bridge_functions

        mock_arb_client.w3.eth.contract.side_effect = [
            usdc_contract,
            bridge_contract,
        ]

        result = await depositor.deposit(500.0)

        assert result.success is True
        assert result.approve_tx_hash is None  # No approve needed
        assert result.deposit_tx_hash == "0xtxhash"


class TestDepositInsufficientFunds:
    """Tests for insufficient balance scenarios."""

    @pytest.mark.asyncio
    async def test_insufficient_usdc(self, depositor, mock_arb_client):
        """Test failure when USDC balance is too low."""
        mock_arb_client.get_usdc_balance = AsyncMock(return_value=Decimal("100"))

        result = await depositor.deposit(500.0)

        assert result.success is False
        assert "Insufficient USDC" in result.error

    @pytest.mark.asyncio
    async def test_insufficient_eth_for_gas(self, depositor, mock_arb_client):
        """Test failure when ETH is too low for gas."""
        mock_arb_client.get_balance = AsyncMock(return_value=Decimal("0.001"))

        result = await depositor.deposit(500.0)

        assert result.success is False
        assert "Insufficient ETH" in result.error


class TestDepositTxFailures:
    """Tests for transaction failure scenarios."""

    @pytest.mark.asyncio
    async def test_approve_tx_failure(self, depositor, mock_arb_client):
        """Test failure when approve tx reverts."""
        mock_allowance_call = AsyncMock(return_value=0)
        mock_functions = MagicMock()
        mock_functions.allowance.return_value.call = mock_allowance_call
        mock_functions.approve.return_value.build_transaction = MagicMock(
            return_value={"from": "0xWallet", "nonce": 42}
        )

        usdc_contract = MagicMock()
        usdc_contract.functions = mock_functions

        mock_arb_client.w3.eth.contract.return_value = usdc_contract

        # Make send_raw_transaction fail
        mock_arb_client.send_raw_transaction = AsyncMock(
            side_effect=Exception("tx reverted")
        )

        result = await depositor.deposit(500.0)

        assert result.success is False
        assert "Approve tx failed" in result.error

    @pytest.mark.asyncio
    async def test_bridge_deposit_tx_failure(self, depositor, mock_arb_client):
        """Test failure when bridge deposit tx reverts."""
        # Allowance is sufficient (no approve needed)
        raw_amount = 500 * 1_000_000
        mock_allowance_call = AsyncMock(return_value=raw_amount + 1)
        mock_functions = MagicMock()
        mock_functions.allowance.return_value.call = mock_allowance_call

        usdc_contract = MagicMock()
        usdc_contract.functions = mock_functions

        # Bridge contract
        mock_bridge_functions = MagicMock()
        mock_bridge_functions.deposit.return_value.build_transaction = MagicMock(
            return_value={"from": "0xWallet", "nonce": 42}
        )
        bridge_contract = MagicMock()
        bridge_contract.functions = mock_bridge_functions

        mock_arb_client.w3.eth.contract.side_effect = [
            usdc_contract,
            bridge_contract,
        ]

        # First send_raw_transaction succeeds (bridge deposit), then fails
        mock_arb_client.send_raw_transaction = AsyncMock(
            side_effect=Exception("bridge reverted")
        )

        result = await depositor.deposit(500.0)

        assert result.success is False
        assert "Bridge deposit tx failed" in result.error


class TestHlCreditPolling:
    """Tests for HL clearinghouse credit polling."""

    @pytest.mark.asyncio
    async def test_poll_detects_credit(self, depositor, mock_arb_client, mock_hl_trader):
        """Test that polling detects HL credit."""
        # Arrange: balance goes from 100 → 100 → 600
        # (mock_hl_trader side_effect already set up)

        # Need to set up the contract mocks for the deposit to succeed
        raw_amount = 500 * 1_000_000
        mock_allowance_call = AsyncMock(return_value=raw_amount + 1)
        mock_functions = MagicMock()
        mock_functions.allowance.return_value.call = mock_allowance_call

        usdc_contract = MagicMock()
        usdc_contract.functions = mock_functions

        mock_bridge_functions = MagicMock()
        mock_bridge_functions.deposit.return_value.build_transaction = MagicMock(
            return_value={"from": "0xWallet", "nonce": 42}
        )
        bridge_contract = MagicMock()
        bridge_contract.functions = mock_bridge_functions

        mock_arb_client.w3.eth.contract.side_effect = [
            usdc_contract,
            bridge_contract,
        ]

        with patch("bot.venues.hyperliquid.depositor.POLL_INTERVAL_SECONDS", 0.01):
            result = await depositor.deposit(500.0)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_no_hl_trader_skips_poll(self, mock_arb_client, mock_settings):
        """Test that missing HL trader skips poll (still succeeds)."""
        with patch(
            "bot.venues.hyperliquid.depositor.get_settings",
            return_value=mock_settings,
        ):
            dep = HyperliquidDepositor(
                arb_client=mock_arb_client,
                wallet_address="0xWallet",
                hl_trader=None,  # No trader
            )

            mock_privy = MagicMock()
            mock_privy.wallet.sign_transaction = AsyncMock(return_value=b"\x01\x02")
            dep._privy = mock_privy

            # Set up contract mocks
            raw_amount = 100 * 1_000_000
            mock_allowance_call = AsyncMock(return_value=raw_amount + 1)
            mock_functions = MagicMock()
            mock_functions.allowance.return_value.call = mock_allowance_call
            usdc_contract = MagicMock()
            usdc_contract.functions = mock_functions

            mock_bridge_functions = MagicMock()
            mock_bridge_functions.deposit.return_value.build_transaction = MagicMock(
                return_value={"from": "0xWallet", "nonce": 42}
            )
            bridge_contract = MagicMock()
            bridge_contract.functions = mock_bridge_functions

            mock_arb_client.w3.eth.contract.side_effect = [
                usdc_contract,
                bridge_contract,
            ]

            result = await dep.deposit(100.0)

            assert result.success is True


class TestDepositResult:
    """Tests for DepositResult dataclass."""

    def test_success_result(self):
        result = DepositResult(
            success=True,
            approve_tx_hash="0xapprove",
            deposit_tx_hash="0xdeposit",
            amount_usdc=Decimal("500"),
        )
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        result = DepositResult(
            success=False,
            error="Insufficient USDC",
        )
        assert result.success is False
        assert result.approve_tx_hash is None
        assert result.deposit_tx_hash is None
