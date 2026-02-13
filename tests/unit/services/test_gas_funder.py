"""Tests for gas funder service."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from bot.services.gas_funder import GasFunder, _load_funder_key


# A valid test private key (DO NOT use in production)
TEST_PRIVATE_KEY = "0x" + "ab" * 32


class TestGasFunderInit:

    @patch("bot.services.gas_funder._load_funder_key", return_value=TEST_PRIVATE_KEY)
    @patch("bot.services.gas_funder.get_settings")
    def test_init_with_loaded_key(self, mock_settings, mock_load):
        mock_settings.return_value = MagicMock(arbitrum_rpc_url=None)
        funder = GasFunder()
        assert funder.funder_address is not None
        assert funder._top_up == Decimal("0.005")
        assert funder._min_balance == Decimal("0.002")

    def test_init_with_explicit_key(self):
        with patch("bot.services.gas_funder.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(arbitrum_rpc_url=None)
            funder = GasFunder(private_key=TEST_PRIVATE_KEY)
            assert funder.funder_address is not None

    def test_init_without_key_raises(self):
        with patch("bot.services.gas_funder._load_funder_key", return_value=None):
            with pytest.raises(ValueError, match="Gas funder private key"):
                GasFunder()


class TestCheckAndFund:

    @pytest.fixture
    def funder(self):
        with patch("bot.services.gas_funder.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(arbitrum_rpc_url=None)
            f = GasFunder(
                private_key=TEST_PRIVATE_KEY,
                top_up_amount=Decimal("0.005"),
                min_balance=Decimal("0.002"),
            )
            # Mock web3 methods
            f._w3 = MagicMock()
            f._w3.eth = MagicMock()
            f._w3.to_checksum_address = lambda addr: addr
            return f

    @pytest.mark.asyncio
    async def test_funds_low_balance_user(self, funder):
        """Should send ETH to user with low balance."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[
            {"id": "user1", "server_evm_address": "0xUser1"},
        ])

        # Mock get_balance and get_funder_balance
        funder.get_funder_balance = AsyncMock(side_effect=[
            Decimal("1.0"),    # initial check
            Decimal("0.995"),  # recheck before send
        ])
        funder.get_balance = AsyncMock(return_value=Decimal("0.001"))  # user below threshold
        funder.send_eth = AsyncMock(return_value="0xtxhash")

        result = await funder.check_and_fund_users(db)

        assert result["checked"] == 1
        assert result["funded"] == 1
        assert result["errors"] == 0
        funder.send_eth.assert_called_once_with("0xUser1", Decimal("0.005"))

    @pytest.mark.asyncio
    async def test_skips_sufficient_balance_user(self, funder):
        """Should not send ETH to user with sufficient balance."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[
            {"id": "user1", "server_evm_address": "0xUser1"},
        ])

        funder.get_funder_balance = AsyncMock(return_value=Decimal("1.0"))
        funder.get_balance = AsyncMock(return_value=Decimal("0.01"))  # above threshold
        funder.send_eth = AsyncMock()

        result = await funder.check_and_fund_users(db)

        assert result["checked"] == 1
        assert result["funded"] == 0
        funder.send_eth.assert_not_called()

    @pytest.mark.asyncio
    async def test_stops_when_funder_low(self, funder):
        """Should stop funding when funder balance is too low."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[
            {"id": "user1", "server_evm_address": "0xUser1"},
        ])

        funder.get_funder_balance = AsyncMock(return_value=Decimal("0.001"))

        result = await funder.check_and_fund_users(db)

        assert result["error"] == "funder low balance"
        assert result["funded"] == 0

    @pytest.mark.asyncio
    async def test_handles_send_error(self, funder):
        """Should continue after individual send failures."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[
            {"id": "user1", "server_evm_address": "0xUser1"},
            {"id": "user2", "server_evm_address": "0xUser2"},
        ])

        funder.get_funder_balance = AsyncMock(side_effect=[
            Decimal("1.0"),    # initial
            Decimal("0.995"),  # recheck before user1
            Decimal("0.990"),  # recheck before user2
        ])
        funder.get_balance = AsyncMock(return_value=Decimal("0.001"))
        funder.send_eth = AsyncMock(side_effect=Exception("tx failed"))

        result = await funder.check_and_fund_users(db)

        assert result["errors"] == 2

    @pytest.mark.asyncio
    async def test_no_users(self, funder):
        """Should handle empty user list."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[])

        funder.get_funder_balance = AsyncMock(return_value=Decimal("1.0"))

        result = await funder.check_and_fund_users(db)

        assert result["checked"] == 0
        assert result["funded"] == 0
