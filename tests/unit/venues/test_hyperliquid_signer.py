"""Tests for Hyperliquid signer via Privy."""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from bot.venues.hyperliquid.signer import HyperliquidSigner, SignedAction


@pytest.fixture
def mock_privy_client():
    """Create mocked Privy wallet signer."""
    with patch('bot.venues.privy_signer.PrivyWalletSigner') as mock_cls:
        signer = Mock()
        # Return a 65-byte hex signature (r[32] + s[32] + v[1])
        sig = "0x" + "ab" * 32 + "cd" * 32 + "1b"
        signer.sign_typed_data_v4 = Mock(return_value=sig)
        mock_cls.return_value = signer
        yield signer


@pytest.fixture
def mock_settings():
    """Mock settings with Privy config."""
    with patch('bot.venues.hyperliquid.signer.get_settings') as mock:
        settings = Mock()
        settings.privy_app_id = "test-app-id"
        settings.privy_app_secret = "test-secret"
        settings.privy_auth_key_path = "test_auth.pem"
        settings.wallet_address = "0x1234567890abcdef"
        mock.return_value = settings
        yield settings


class TestHyperliquidSigner:
    """Test Hyperliquid signer with Privy."""

    def test_init(self, mock_privy_client, mock_settings):
        """Test signer initialization."""
        signer = HyperliquidSigner()
        assert signer.address == "0x1234567890abcdef"

    def test_domain_config(self, mock_privy_client, mock_settings):
        """Test that domain matches Hyperliquid SDK."""
        signer = HyperliquidSigner()
        assert signer.DOMAIN["name"] == "Exchange"
        assert signer.DOMAIN["chainId"] == 1337
        assert signer.DOMAIN["version"] == "1"

    @pytest.mark.asyncio
    async def test_sign_order(self, mock_privy_client, mock_settings):
        """Test signing an order via phantom agent pattern."""
        signer = HyperliquidSigner()

        signed = await signer.sign_order(
            asset_index=4,  # SOL
            is_buy=False,
            sz="10.0",
            limit_px="100.0",
            order_type={"limit": {"tif": "Ioc"}},
        )

        assert isinstance(signed, SignedAction)
        assert signed.action["type"] == "order"
        assert signed.action["grouping"] == "na"
        assert len(signed.action["orders"]) == 1

        order = signed.action["orders"][0]
        assert order["a"] == 4
        assert order["b"] is False
        assert order["s"] == "10.0"
        assert order["p"] == "100.0"
        assert order["r"] is False
        assert order["t"] == {"limit": {"tif": "Ioc"}}

        # Signature should be parsed into {r, s, v}
        assert "r" in signed.signature
        assert "s" in signed.signature
        assert "v" in signed.signature

        # Verify Privy was called with Agent type (phantom agent)
        mock_privy_client.sign_typed_data_v4.assert_called_once()
        call_kwargs = mock_privy_client.sign_typed_data_v4.call_args.kwargs
        assert call_kwargs["primary_type"] == "Agent"
        assert call_kwargs["domain"]["name"] == "Exchange"

    @pytest.mark.asyncio
    async def test_sign_order_error(self, mock_privy_client, mock_settings):
        """Test error handling when Privy fails."""
        mock_privy_client.sign_typed_data_v4.side_effect = Exception("Privy error")

        signer = HyperliquidSigner()

        with pytest.raises(Exception, match="Privy error"):
            await signer.sign_order(
                asset_index=1,
                is_buy=True,
                sz="1.0",
                limit_px="50.0",
                order_type={"limit": {"tif": "Ioc"}},
            )


class TestSignLeverageUpdate:
    """Tests for leverage update signing."""

    @pytest.mark.asyncio
    async def test_sign_leverage_update(self, mock_privy_client, mock_settings):
        """Test signing a leverage update."""
        signer = HyperliquidSigner()

        signed = await signer.sign_leverage_update(
            asset_index=4,
            leverage=3,
            is_cross=True,
        )

        assert isinstance(signed, SignedAction)
        assert signed.action["type"] == "updateLeverage"
        assert signed.action["asset"] == 4
        assert signed.action["leverage"] == 3
        assert signed.action["isCross"] is True


class TestSignUsdClassTransfer:
    """Tests for spot<->perp USDC transfer signing."""

    @pytest.mark.asyncio
    async def test_sign_usd_class_transfer(self, mock_privy_client, mock_settings):
        """Test signing a usdClassTransfer."""
        signer = HyperliquidSigner()

        signed = await signer.sign_usd_class_transfer(
            amount="1000.00",
            to_perp=True,
        )

        assert isinstance(signed, SignedAction)
        assert signed.action["type"] == "usdClassTransfer"
        assert signed.action["amount"] == "1000.00"
        assert signed.action["toPerp"] is True
        assert signed.action["hyperliquidChain"] == "Mainnet"

        # User-signed actions use different domain
        call_kwargs = mock_privy_client.sign_typed_data_v4.call_args.kwargs
        assert call_kwargs["domain"]["name"] == "HyperliquidSignTransaction"
        assert call_kwargs["domain"]["chainId"] == 42161


class TestPhantomAgent:
    """Tests for the phantom agent signing mechanism."""

    def test_action_hash_deterministic(self, mock_privy_client, mock_settings):
        """Test that action hash is deterministic."""
        signer = HyperliquidSigner()

        action = {"type": "order", "orders": [{"a": 4, "b": False, "p": "100.0", "s": "10.0", "r": False, "t": {"limit": {"tif": "Ioc"}}}], "grouping": "na"}
        nonce = 1234567890000

        hash1 = signer._action_hash(action, None, nonce)
        hash2 = signer._action_hash(action, None, nonce)

        assert hash1 == hash2
        assert len(hash1) == 32  # keccak256 output

    def test_construct_phantom_agent(self, mock_privy_client, mock_settings):
        """Test phantom agent construction."""
        signer = HyperliquidSigner()

        hash_bytes = b"\x01" * 32
        agent = signer._construct_phantom_agent(hash_bytes)

        assert agent["source"] == "a"  # mainnet
        assert agent["connectionId"] == hash_bytes


class TestParseSignature:
    """Tests for signature parsing."""

    def test_parse_hex_signature(self, mock_privy_client, mock_settings):
        """Test parsing a hex signature into r, s, v."""
        signer = HyperliquidSigner()

        r_bytes = b"\xaa" * 32
        s_bytes = b"\xbb" * 32
        v_byte = bytes([27])
        sig_hex = "0x" + (r_bytes + s_bytes + v_byte).hex()

        parsed = signer._parse_signature(sig_hex)

        assert parsed["r"] == "0x" + r_bytes.hex()
        assert parsed["s"] == "0x" + s_bytes.hex()
        assert parsed["v"] == 27

    def test_parse_dict_signature(self, mock_privy_client, mock_settings):
        """Test that dict signatures pass through."""
        signer = HyperliquidSigner()

        sig_dict = {"r": "0xabc", "s": "0xdef", "v": 28}
        parsed = signer._parse_signature(sig_dict)

        assert parsed == sig_dict

    def test_parse_normalize_v(self, mock_privy_client, mock_settings):
        """Test that v=0/1 is normalized to 27/28."""
        signer = HyperliquidSigner()

        sig_hex = "0x" + "aa" * 32 + "bb" * 32 + "00"  # v=0
        parsed = signer._parse_signature(sig_hex)
        assert parsed["v"] == 27

    def test_old_names_no_longer_exist(self):
        """Verify old SignedOrder/SignedSpotTransfer names are gone."""
        import bot.venues.hyperliquid.signer as signer_module
        assert not hasattr(signer_module, "SignedOrder")
        assert not hasattr(signer_module, "SignedSpotTransfer")
