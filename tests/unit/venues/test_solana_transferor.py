"""Tests for SolanaTransferor — SOL and USDC transfers on Solana."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from bot.venues.solana_transferor import (
    SolanaTransferor,
    SolTransferResult,
    MIN_SOL_RESERVE,
)

# Valid Solana pubkey strings for testing
WALLET_ADDR = "11111111111111111111111111111111"
DEST_ADDR = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


@pytest.fixture
def mock_sol_client():
    client = MagicMock()
    client.get_balance = AsyncMock(return_value=1.5)  # 1.5 SOL
    client.get_token_balance = AsyncMock(return_value=500.0)  # 500 USDC
    client.get_latest_blockhash = AsyncMock(
        return_value="11111111111111111111111111111111"
    )
    client.send_transaction = AsyncMock(return_value="5xSig123abc")
    client.confirm_transaction = AsyncMock(return_value=True)
    return client


@pytest.fixture
def transferor(mock_sol_client):
    t = SolanaTransferor(
        sol_client=mock_sol_client,
        wallet_address=WALLET_ADDR,
        wallet_id="test-wallet-id",
        user_id="test-user",
    )
    return t


class TestTransferSolTo:
    """Tests for native SOL transfers."""

    @pytest.mark.asyncio
    async def test_successful_sol_transfer(self, transferor):
        with patch.object(
            transferor, "_build_sign_send", new_callable=AsyncMock, return_value="5xSig123abc"
        ):
            result = await transferor.transfer_sol_to(DEST_ADDR, 0.5)

        assert result.success is True
        assert result.signature == "5xSig123abc"
        assert result.amount == Decimal("0.5")
        assert result.error is None

    @pytest.mark.asyncio
    async def test_insufficient_sol_balance(self, transferor, mock_sol_client):
        mock_sol_client.get_balance = AsyncMock(return_value=0.005)

        result = await transferor.transfer_sol_to(DEST_ADDR, 0.5)

        assert result.success is False
        assert "Insufficient SOL" in result.error

    @pytest.mark.asyncio
    async def test_sol_transfer_tx_failure(self, transferor):
        with patch.object(
            transferor, "_build_sign_send",
            new_callable=AsyncMock, side_effect=Exception("tx failed"),
        ):
            result = await transferor.transfer_sol_to(DEST_ADDR, 0.1)

        assert result.success is False
        assert "SOL transfer failed" in result.error

    @pytest.mark.asyncio
    async def test_sol_transfer_confirmation_timeout(self, transferor):
        with patch.object(
            transferor, "_build_sign_send",
            new_callable=AsyncMock,
            side_effect=Exception("Transaction not confirmed within timeout: sig"),
        ):
            result = await transferor.transfer_sol_to(DEST_ADDR, 0.1)

        assert result.success is False
        assert "not confirmed" in result.error


class TestTransferUsdcTo:
    """Tests for USDC (SPL) transfers."""

    @pytest.mark.asyncio
    async def test_successful_usdc_transfer(self, transferor):
        with patch.object(
            transferor, "_build_sign_send", new_callable=AsyncMock, return_value="5xSig123abc"
        ):
            result = await transferor.transfer_usdc_to(DEST_ADDR, 100.0)

        assert result.success is True
        assert result.signature == "5xSig123abc"
        assert result.amount == Decimal("100")

    @pytest.mark.asyncio
    async def test_insufficient_usdc(self, transferor, mock_sol_client):
        mock_sol_client.get_token_balance = AsyncMock(return_value=10.0)

        result = await transferor.transfer_usdc_to(DEST_ADDR, 100.0)

        assert result.success is False
        assert "Insufficient USDC" in result.error

    @pytest.mark.asyncio
    async def test_insufficient_sol_for_fees(self, transferor, mock_sol_client):
        mock_sol_client.get_balance = AsyncMock(return_value=0.001)

        result = await transferor.transfer_usdc_to(DEST_ADDR, 100.0)

        assert result.success is False
        assert "Insufficient SOL" in result.error

    @pytest.mark.asyncio
    async def test_usdc_transfer_tx_failure(self, transferor, mock_sol_client):
        # Set balances high enough to pass validation
        mock_sol_client.get_token_balance = AsyncMock(return_value=500.0)
        mock_sol_client.get_balance = AsyncMock(return_value=1.0)

        with patch.object(
            transferor, "_build_sign_send",
            new_callable=AsyncMock, side_effect=Exception("tx reverted"),
        ):
            result = await transferor.transfer_usdc_to(DEST_ADDR, 50.0)

        assert result.success is False
        assert "USDC transfer failed" in result.error


class TestSolTransferResult:
    """Tests for result dataclass."""

    def test_success_result(self):
        result = SolTransferResult(
            success=True,
            signature="5xSig123",
            amount=Decimal("1.5"),
        )
        assert result.success is True
        assert result.signature == "5xSig123"
        assert result.error is None

    def test_failure_result(self):
        result = SolTransferResult(
            success=False,
            error="Insufficient SOL",
        )
        assert result.success is False
        assert result.signature is None
        assert result.amount is None
