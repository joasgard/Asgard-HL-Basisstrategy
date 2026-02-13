"""
Tests for ArbitrumClient ERC-20 balance methods.

Covers:
- get_erc20_balance() with various tokens/decimals
- get_usdc_balance() convenience wrapper
- send_raw_transaction() bug fix (signed_tx_bytes param)
- Edge cases: zero balance, large balance, missing address
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from shared.chain.arbitrum import (
    ArbitrumClient,
    NATIVE_USDC_ARBITRUM,
    ERC20_BALANCE_OF_ABI,
)


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.arbitrum_rpc_url = "https://arb1.arbitrum.io/rpc"
    settings.wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEbE"
    return settings


@pytest.fixture
def arb_client(mock_settings):
    """Create ArbitrumClient with mocked Web3."""
    with patch("shared.chain.arbitrum.get_settings", return_value=mock_settings):
        with patch("shared.chain.arbitrum.AsyncWeb3") as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.to_checksum_address = lambda addr: addr
            mock_w3_class.return_value = mock_w3
            mock_w3_class.AsyncHTTPProvider = MagicMock()

            client = ArbitrumClient()
            yield client


class TestNativeUsdcConstant:
    """Tests for the NATIVE_USDC_ARBITRUM constant."""

    def test_native_usdc_address(self):
        """Verify the native USDC address is correct."""
        assert NATIVE_USDC_ARBITRUM == "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"

    def test_not_bridged_usdc_e(self):
        """Verify it's NOT the old bridged USDC.e address."""
        assert NATIVE_USDC_ARBITRUM != "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8"


class TestErc20BalanceOfAbi:
    """Tests for the ERC20 ABI."""

    def test_abi_has_balance_of(self):
        """Test ABI contains balanceOf function."""
        assert len(ERC20_BALANCE_OF_ABI) == 1
        assert ERC20_BALANCE_OF_ABI[0]["name"] == "balanceOf"
        assert ERC20_BALANCE_OF_ABI[0]["type"] == "function"


class TestGetErc20Balance:
    """Tests for get_erc20_balance method."""

    @pytest.mark.asyncio
    async def test_basic_balance(self, mock_settings):
        """Test reading a basic ERC-20 balance."""
        with patch("shared.chain.arbitrum.get_settings", return_value=mock_settings):
            with patch("shared.chain.arbitrum.AsyncWeb3") as mock_w3_class:
                mock_w3 = MagicMock()
                mock_w3.to_checksum_address = lambda addr: addr

                # Mock contract call chain
                mock_balance_of = AsyncMock(return_value=1_000_000)  # 1 USDC raw
                mock_functions = MagicMock()
                mock_functions.balanceOf.return_value.call = mock_balance_of
                mock_contract = MagicMock()
                mock_contract.functions = mock_functions
                mock_w3.eth.contract.return_value = mock_contract

                mock_w3_class.return_value = mock_w3

                client = ArbitrumClient()
                balance = await client.get_erc20_balance(
                    token_address=NATIVE_USDC_ARBITRUM,
                    owner_address="0xOwner",
                    decimals=6,
                )

                assert balance == Decimal("1")
                mock_functions.balanceOf.assert_called_once_with("0xOwner")

    @pytest.mark.asyncio
    async def test_18_decimal_token(self, mock_settings):
        """Test reading an 18-decimal token (e.g. WETH)."""
        with patch("shared.chain.arbitrum.get_settings", return_value=mock_settings):
            with patch("shared.chain.arbitrum.AsyncWeb3") as mock_w3_class:
                mock_w3 = MagicMock()
                mock_w3.to_checksum_address = lambda addr: addr

                mock_balance_of = AsyncMock(return_value=2 * 10**18)  # 2 tokens
                mock_functions = MagicMock()
                mock_functions.balanceOf.return_value.call = mock_balance_of
                mock_contract = MagicMock()
                mock_contract.functions = mock_functions
                mock_w3.eth.contract.return_value = mock_contract

                mock_w3_class.return_value = mock_w3

                client = ArbitrumClient()
                balance = await client.get_erc20_balance(
                    token_address="0xSomeToken",
                    owner_address="0xOwner",
                    decimals=18,
                )

                assert balance == Decimal("2")

    @pytest.mark.asyncio
    async def test_zero_balance(self, mock_settings):
        """Test zero balance returns Decimal(0)."""
        with patch("shared.chain.arbitrum.get_settings", return_value=mock_settings):
            with patch("shared.chain.arbitrum.AsyncWeb3") as mock_w3_class:
                mock_w3 = MagicMock()
                mock_w3.to_checksum_address = lambda addr: addr

                mock_balance_of = AsyncMock(return_value=0)
                mock_functions = MagicMock()
                mock_functions.balanceOf.return_value.call = mock_balance_of
                mock_contract = MagicMock()
                mock_contract.functions = mock_functions
                mock_w3.eth.contract.return_value = mock_contract

                mock_w3_class.return_value = mock_w3

                client = ArbitrumClient()
                balance = await client.get_erc20_balance(
                    token_address="0xToken",
                    owner_address="0xOwner",
                    decimals=6,
                )

                assert balance == Decimal("0")

    @pytest.mark.asyncio
    async def test_large_balance(self, mock_settings):
        """Test reading a very large balance."""
        with patch("shared.chain.arbitrum.get_settings", return_value=mock_settings):
            with patch("shared.chain.arbitrum.AsyncWeb3") as mock_w3_class:
                mock_w3 = MagicMock()
                mock_w3.to_checksum_address = lambda addr: addr

                # 1 million USDC
                mock_balance_of = AsyncMock(return_value=1_000_000 * 10**6)
                mock_functions = MagicMock()
                mock_functions.balanceOf.return_value.call = mock_balance_of
                mock_contract = MagicMock()
                mock_contract.functions = mock_functions
                mock_w3.eth.contract.return_value = mock_contract

                mock_w3_class.return_value = mock_w3

                client = ArbitrumClient()
                balance = await client.get_erc20_balance(
                    token_address="0xToken",
                    owner_address="0xOwner",
                    decimals=6,
                )

                assert balance == Decimal("1000000")

    @pytest.mark.asyncio
    async def test_uses_default_wallet_address(self, mock_settings):
        """Test that default wallet address is used when none provided."""
        with patch("shared.chain.arbitrum.get_settings", return_value=mock_settings):
            with patch("shared.chain.arbitrum.AsyncWeb3") as mock_w3_class:
                mock_w3 = MagicMock()
                mock_w3.to_checksum_address = lambda addr: addr

                mock_balance_of = AsyncMock(return_value=500_000)
                mock_functions = MagicMock()
                mock_functions.balanceOf.return_value.call = mock_balance_of
                mock_contract = MagicMock()
                mock_contract.functions = mock_functions
                mock_w3.eth.contract.return_value = mock_contract

                mock_w3_class.return_value = mock_w3

                client = ArbitrumClient()
                balance = await client.get_erc20_balance(
                    token_address="0xToken",
                    decimals=6,
                )

                # Should use the wallet_address from settings (not a custom address)
                mock_functions.balanceOf.assert_called_once()
                actual_addr = mock_functions.balanceOf.call_args[0][0]
                assert actual_addr == client.wallet_address


class TestGetUsdcBalance:
    """Tests for get_usdc_balance convenience wrapper."""

    @pytest.mark.asyncio
    async def test_usdc_balance(self, mock_settings):
        """Test that get_usdc_balance uses correct token and decimals."""
        with patch("shared.chain.arbitrum.get_settings", return_value=mock_settings):
            with patch("shared.chain.arbitrum.AsyncWeb3") as mock_w3_class:
                mock_w3 = MagicMock()
                mock_w3.to_checksum_address = lambda addr: addr

                mock_balance_of = AsyncMock(return_value=5_000_000)  # 5 USDC
                mock_functions = MagicMock()
                mock_functions.balanceOf.return_value.call = mock_balance_of
                mock_contract = MagicMock()
                mock_contract.functions = mock_functions
                mock_w3.eth.contract.return_value = mock_contract

                mock_w3_class.return_value = mock_w3

                client = ArbitrumClient()
                balance = await client.get_usdc_balance("0xOwner")

                assert balance == Decimal("5")
                # Verify native USDC address was used
                call_args = mock_w3.eth.contract.call_args
                assert call_args.kwargs["address"] == NATIVE_USDC_ARBITRUM

    @pytest.mark.asyncio
    async def test_usdc_fractional(self, mock_settings):
        """Test USDC fractional amounts."""
        with patch("shared.chain.arbitrum.get_settings", return_value=mock_settings):
            with patch("shared.chain.arbitrum.AsyncWeb3") as mock_w3_class:
                mock_w3 = MagicMock()
                mock_w3.to_checksum_address = lambda addr: addr

                mock_balance_of = AsyncMock(return_value=1_500_000)  # 1.5 USDC
                mock_functions = MagicMock()
                mock_functions.balanceOf.return_value.call = mock_balance_of
                mock_contract = MagicMock()
                mock_contract.functions = mock_functions
                mock_w3.eth.contract.return_value = mock_contract

                mock_w3_class.return_value = mock_w3

                client = ArbitrumClient()
                balance = await client.get_usdc_balance("0xOwner")

                assert balance == Decimal("1.5")


class TestSendRawTransactionFix:
    """Test that send_raw_transaction uses the correct parameter."""

    @pytest.mark.asyncio
    async def test_send_raw_transaction_uses_param(self, mock_settings):
        """Test that send_raw_transaction uses signed_tx_bytes, not signed_tx."""
        with patch("shared.chain.arbitrum.get_settings", return_value=mock_settings):
            with patch("shared.chain.arbitrum.AsyncWeb3") as mock_w3_class:
                mock_w3 = MagicMock()
                mock_tx_hash = MagicMock()
                mock_tx_hash.hex.return_value = "0xdeadbeef"
                mock_w3.eth.send_raw_transaction = AsyncMock(return_value=mock_tx_hash)
                mock_w3_class.return_value = mock_w3

                client = ArbitrumClient()
                raw_bytes = b"\x01\x02\x03"
                tx_hash = await client.send_raw_transaction(raw_bytes)

                # Verify the bytes param was passed directly
                mock_w3.eth.send_raw_transaction.assert_called_once_with(raw_bytes)
                assert tx_hash == "0xdeadbeef"
