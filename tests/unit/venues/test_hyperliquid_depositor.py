"""
Tests for HyperliquidDepositor — Arbitrum ↔ HL deposit/withdraw flows.

Covers:
- Full deposit happy path (USDC transfer to bridge + poll)
- Insufficient USDC on Arbitrum
- Insufficient ETH for gas
- Bridge transfer tx failure
- HL credit polling timeout
- No HL trader (skips poll)
- Withdrawal happy path
- Withdrawal with insufficient HL balance
- Withdrawal with no HL trader configured
- Withdrawal submission failure
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from bot.venues.hyperliquid.depositor import (
    HyperliquidDepositor,
    DepositResult,
    TransferResult,
    WithdrawResult,
    MIN_ETH_FOR_BRIDGE,
)


@pytest.fixture
def mock_arb_client():
    """Create a mocked ArbitrumClient."""
    client = MagicMock()
    client.w3 = MagicMock()
    client.w3.to_checksum_address = lambda addr: addr

    # Default: enough USDC and ETH
    client.get_usdc_balance = AsyncMock(return_value=Decimal("1000"))
    client.get_balance = AsyncMock(return_value=Decimal("0.05"))
    client.get_transaction_count = AsyncMock(return_value=42)
    client.get_gas_price = AsyncMock(return_value=100_000_000)  # 0.1 gwei
    client.send_raw_transaction = AsyncMock(return_value="0xtxhash")
    client.wait_for_transaction_receipt = AsyncMock(return_value={"status": 1})

    return client


def _mock_usdc_contract():
    """Create a mocked USDC contract with transfer function."""
    mock_functions = MagicMock()
    mock_functions.transfer.return_value.build_transaction = AsyncMock(
        return_value={"from": "0xWallet", "nonce": 42}
    )
    contract = MagicMock()
    contract.functions = mock_functions
    return contract


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

        # Mock the Privy wallet signer
        mock_privy = MagicMock()
        mock_privy.sign_eth_transaction = MagicMock(return_value="0x0102")
        dep._privy = mock_privy

        return dep


class TestDepositHappyPath:
    """Tests for successful deposit flow."""

    @pytest.mark.asyncio
    async def test_full_deposit_with_transfer(self, depositor, mock_arb_client):
        """Test full flow: USDC transfer to bridge + poll."""
        usdc_contract = _mock_usdc_contract()
        mock_arb_client.w3.eth.contract.return_value = usdc_contract

        result = await depositor.deposit(500.0)

        assert result.success is True
        assert result.approve_tx_hash is None  # no approve in transfer flow
        assert result.deposit_tx_hash == "0xtxhash"
        assert result.amount_usdc == Decimal("500")

    @pytest.mark.asyncio
    async def test_deposit_calls_transfer(self, depositor, mock_arb_client):
        """Test that deposit calls USDC transfer(bridge, amount)."""
        usdc_contract = _mock_usdc_contract()
        mock_arb_client.w3.eth.contract.return_value = usdc_contract

        await depositor.deposit(500.0)

        # Verify transfer was called with bridge address and raw amount
        usdc_contract.functions.transfer.assert_called_once_with(
            "0xBridgeContract", 500_000_000
        )


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
    async def test_bridge_transfer_tx_failure(self, depositor, mock_arb_client):
        """Test failure when USDC transfer tx reverts."""
        usdc_contract = _mock_usdc_contract()
        mock_arb_client.w3.eth.contract.return_value = usdc_contract

        # Make send_raw_transaction fail
        mock_arb_client.send_raw_transaction = AsyncMock(
            side_effect=Exception("tx reverted")
        )

        result = await depositor.deposit(500.0)

        assert result.success is False
        assert "Bridge transfer tx failed" in result.error


class TestHlCreditPolling:
    """Tests for HL clearinghouse credit polling."""

    @pytest.mark.asyncio
    async def test_poll_detects_credit(self, depositor, mock_arb_client, mock_hl_trader):
        """Test that polling detects HL credit."""
        usdc_contract = _mock_usdc_contract()
        mock_arb_client.w3.eth.contract.return_value = usdc_contract

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
            mock_privy.sign_eth_transaction = MagicMock(return_value="0x0102")
            dep._privy = mock_privy

            usdc_contract = _mock_usdc_contract()
            mock_arb_client.w3.eth.contract.return_value = usdc_contract

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


class TestWithdrawHappyPath:
    """Tests for successful withdrawal flow."""

    @pytest.mark.asyncio
    async def test_full_withdraw(self, mock_arb_client, mock_settings):
        """Test full withdrawal: sign + submit + poll Arbitrum credit."""
        mock_signer = AsyncMock()
        mock_signer.sign_user_action = AsyncMock(return_value=MagicMock(
            action={"type": "withdraw3"},
            signature={"r": "0x1", "s": "0x2", "v": 27},
            nonce=1234567890,
        ))

        mock_client = AsyncMock()
        mock_client.exchange = AsyncMock(return_value={"status": "ok"})

        mock_trader = MagicMock()
        mock_trader.get_deposited_balance = AsyncMock(return_value=1000.0)
        mock_trader.signer = mock_signer
        mock_trader.client = mock_client

        # Arb balance goes from 100 → 100 → 600 (credit detected)
        mock_arb_client.get_usdc_balance = AsyncMock(
            side_effect=[Decimal("100"), Decimal("100"), Decimal("600")]
        )

        with patch(
            "bot.venues.hyperliquid.depositor.get_settings",
            return_value=mock_settings,
        ):
            dep = HyperliquidDepositor(
                arb_client=mock_arb_client,
                wallet_address="0xWallet",
                hl_trader=mock_trader,
            )

        with patch("bot.venues.hyperliquid.depositor.POLL_INTERVAL_SECONDS", 0.01):
            result = await dep.withdraw(500.0)

        assert result.success is True
        assert result.amount_usdc == Decimal("500")

        # Verify the signer was called with withdraw3 action
        mock_signer.sign_user_action.assert_called_once()
        call_kwargs = mock_signer.sign_user_action.call_args
        assert call_kwargs.kwargs["action"]["type"] == "withdraw3"
        assert call_kwargs.kwargs["action"]["destination"] == "0xWallet"
        assert call_kwargs.kwargs["primary_type"] == "HyperliquidTransaction:Withdraw"

        # Verify exchange was called
        mock_client.exchange.assert_called_once()


class TestWithdrawInsufficientFunds:
    """Tests for withdrawal with insufficient HL balance."""

    @pytest.mark.asyncio
    async def test_insufficient_hl_balance(self, mock_arb_client, mock_settings):
        """Test failure when HL balance is too low for withdrawal."""
        mock_trader = MagicMock()
        mock_trader.get_deposited_balance = AsyncMock(return_value=100.0)
        mock_trader.signer = AsyncMock()
        mock_trader.client = AsyncMock()

        with patch(
            "bot.venues.hyperliquid.depositor.get_settings",
            return_value=mock_settings,
        ):
            dep = HyperliquidDepositor(
                arb_client=mock_arb_client,
                wallet_address="0xWallet",
                hl_trader=mock_trader,
            )

        result = await dep.withdraw(500.0)

        assert result.success is False
        assert "Insufficient HL balance" in result.error

    @pytest.mark.asyncio
    async def test_no_hl_trader_fails(self, mock_arb_client, mock_settings):
        """Test failure when no HL trader is configured."""
        with patch(
            "bot.venues.hyperliquid.depositor.get_settings",
            return_value=mock_settings,
        ):
            dep = HyperliquidDepositor(
                arb_client=mock_arb_client,
                wallet_address="0xWallet",
                hl_trader=None,
            )

        result = await dep.withdraw(500.0)

        assert result.success is False
        assert "No HL trader" in result.error


class TestWithdrawFailures:
    """Tests for withdrawal submission failures."""

    @pytest.mark.asyncio
    async def test_exchange_submission_fails(self, mock_arb_client, mock_settings):
        """Test failure when exchange endpoint rejects withdrawal."""
        mock_signer = AsyncMock()
        mock_signer.sign_user_action = AsyncMock(return_value=MagicMock(
            action={"type": "withdraw3"},
            signature={"r": "0x1", "s": "0x2", "v": 27},
            nonce=1234567890,
        ))

        mock_client = AsyncMock()
        mock_client.exchange = AsyncMock(side_effect=Exception("API error"))

        mock_trader = MagicMock()
        mock_trader.get_deposited_balance = AsyncMock(return_value=1000.0)
        mock_trader.signer = mock_signer
        mock_trader.client = mock_client

        with patch(
            "bot.venues.hyperliquid.depositor.get_settings",
            return_value=mock_settings,
        ):
            dep = HyperliquidDepositor(
                arb_client=mock_arb_client,
                wallet_address="0xWallet",
                hl_trader=mock_trader,
            )

        result = await dep.withdraw(500.0)

        assert result.success is False
        assert "submission failed" in result.error

    @pytest.mark.asyncio
    async def test_missing_signer_on_trader(self, mock_arb_client, mock_settings):
        """Test failure when trader has no signer attribute."""
        mock_trader = MagicMock(spec=[])  # Empty spec, no attributes
        mock_trader.get_deposited_balance = AsyncMock(return_value=1000.0)

        with patch(
            "bot.venues.hyperliquid.depositor.get_settings",
            return_value=mock_settings,
        ):
            dep = HyperliquidDepositor(
                arb_client=mock_arb_client,
                wallet_address="0xWallet",
                hl_trader=mock_trader,
            )

        result = await dep.withdraw(500.0)

        assert result.success is False
        assert "missing signer" in result.error


class TestWithdrawResult:
    """Tests for WithdrawResult dataclass."""

    def test_success_result(self):
        result = WithdrawResult(
            success=True,
            amount_usdc=Decimal("500"),
        )
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        result = WithdrawResult(
            success=False,
            error="Insufficient balance",
        )
        assert result.success is False
        assert result.amount_usdc is None


class TestTransferUsdcTo:
    """Tests for USDC wallet-to-wallet transfer on Arbitrum."""

    @pytest.mark.asyncio
    async def test_successful_transfer(self, depositor, mock_arb_client):
        """Test full transfer: check balances, send USDC transfer tx."""
        usdc_contract = _mock_usdc_contract()
        mock_arb_client.w3.eth.contract.return_value = usdc_contract

        result = await depositor.transfer_usdc_to("0xDestination", 250.0)

        assert result.success is True
        assert result.tx_hash == "0xtxhash"
        assert result.amount_usdc == Decimal("250")
        assert result.error is None

    @pytest.mark.asyncio
    async def test_transfer_calls_correct_destination(self, depositor, mock_arb_client):
        """Test that transfer sends to the given destination, not the bridge."""
        usdc_contract = _mock_usdc_contract()
        mock_arb_client.w3.eth.contract.return_value = usdc_contract

        await depositor.transfer_usdc_to("0xDestination", 100.0)

        # Verify transfer was called with destination (not bridge) and raw amount
        usdc_contract.functions.transfer.assert_called_once_with(
            "0xDestination", 100_000_000
        )

    @pytest.mark.asyncio
    async def test_insufficient_usdc(self, depositor, mock_arb_client):
        """Test failure when USDC balance is too low."""
        mock_arb_client.get_usdc_balance = AsyncMock(return_value=Decimal("50"))

        result = await depositor.transfer_usdc_to("0xDestination", 100.0)

        assert result.success is False
        assert "Insufficient USDC" in result.error

    @pytest.mark.asyncio
    async def test_insufficient_eth_for_gas(self, depositor, mock_arb_client):
        """Test failure when ETH is too low for gas."""
        mock_arb_client.get_balance = AsyncMock(return_value=Decimal("0.0001"))

        result = await depositor.transfer_usdc_to("0xDestination", 100.0)

        assert result.success is False
        assert "Insufficient ETH" in result.error

    @pytest.mark.asyncio
    async def test_transfer_tx_failure(self, depositor, mock_arb_client):
        """Test failure when the transfer tx reverts."""
        usdc_contract = _mock_usdc_contract()
        mock_arb_client.w3.eth.contract.return_value = usdc_contract
        mock_arb_client.send_raw_transaction = AsyncMock(
            side_effect=Exception("tx reverted")
        )

        result = await depositor.transfer_usdc_to("0xDestination", 100.0)

        assert result.success is False
        assert "USDC transfer failed" in result.error


class TestTransferEthTo:
    """Tests for native ETH wallet-to-wallet transfer on Arbitrum."""

    @pytest.mark.asyncio
    async def test_successful_eth_transfer(self, depositor, mock_arb_client):
        """Test full ETH transfer: check balance, send native tx."""
        # Need enough ETH for amount + gas reserve
        mock_arb_client.get_balance = AsyncMock(return_value=Decimal("0.05"))
        mock_arb_client.get_transaction_count = AsyncMock(return_value=0)
        mock_arb_client.get_gas_price = AsyncMock(return_value=100_000_000)  # 0.1 gwei

        result = await depositor.transfer_eth_to("0xDestination", 0.01)

        assert result.success is True
        assert result.tx_hash == "0xtxhash"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_insufficient_eth(self, depositor, mock_arb_client):
        """Test failure when ETH balance too low (need amount + gas)."""
        mock_arb_client.get_balance = AsyncMock(return_value=Decimal("0.001"))

        result = await depositor.transfer_eth_to("0xDestination", 0.01)

        assert result.success is False
        assert "Insufficient ETH" in result.error

    @pytest.mark.asyncio
    async def test_eth_transfer_tx_failure(self, depositor, mock_arb_client):
        """Test failure when the ETH tx reverts."""
        mock_arb_client.get_balance = AsyncMock(return_value=Decimal("0.05"))
        mock_arb_client.get_transaction_count = AsyncMock(return_value=0)
        mock_arb_client.get_gas_price = AsyncMock(return_value=100_000_000)
        mock_arb_client.send_raw_transaction = AsyncMock(
            side_effect=Exception("tx reverted")
        )

        result = await depositor.transfer_eth_to("0xDestination", 0.01)

        assert result.success is False
        assert "ETH transfer failed" in result.error


class TestTransferResult:
    """Tests for TransferResult dataclass."""

    def test_success_result(self):
        result = TransferResult(
            success=True,
            tx_hash="0xabc123",
            amount_usdc=Decimal("500"),
        )
        assert result.success is True
        assert result.tx_hash == "0xabc123"
        assert result.error is None

    def test_failure_result(self):
        result = TransferResult(
            success=False,
            error="Insufficient USDC",
        )
        assert result.success is False
        assert result.tx_hash is None
        assert result.amount_usdc is None
