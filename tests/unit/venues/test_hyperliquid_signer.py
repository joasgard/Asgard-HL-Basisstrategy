"""Tests for Hyperliquid signer via Privy."""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.venues.hyperliquid.signer import HyperliquidSigner, SignedOrder


@pytest.fixture
def mock_privy_client():
    """Create mocked Privy client."""
    with patch('privy.PrivyClient') as mock:
        client = Mock()
        client.wallet = AsyncMock()
        client.wallet.sign_typed_data = AsyncMock(return_value="0xsignature123")
        mock.return_value = client
        yield client


@pytest.fixture
def mock_settings():
    """Mock settings with Privy config."""
    with patch('src.venues.hyperliquid.signer.get_settings') as mock:
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
    
    @pytest.mark.asyncio
    async def test_sign_order(self, mock_privy_client, mock_settings):
        """Test signing an order via Privy."""
        signer = HyperliquidSigner()
        
        signed = await signer.sign_order(
            coin="SOL",
            is_buy=False,
            sz="10.0",
            limit_px="100.0",
            order_type={"limit": {"tif": "Gtc"}},
        )
        
        assert isinstance(signed, SignedOrder)
        assert signed.signature == "0xsignature123"
        assert signed.coin == "SOL"
        assert not signed.is_buy
        
        # Verify Privy was called
        mock_privy_client.wallet.sign_typed_data.assert_called_once()
        call_args = mock_privy_client.wallet.sign_typed_data.call_args
        assert call_args.kwargs['wallet_address'] == "0x1234567890abcdef"
    
    @pytest.mark.asyncio
    async def test_sign_order_error(self, mock_privy_client, mock_settings):
        """Test error handling when Privy fails."""
        mock_privy_client.wallet.sign_typed_data.side_effect = Exception("Privy error")
        
        signer = HyperliquidSigner()
        
        with pytest.raises(Exception, match="Privy error"):
            await signer.sign_order(
                coin="SOL",
                is_buy=True,
                sz="1.0",
                limit_px="50.0",
                order_type={"market": {}},
            )


class TestSignedOrder:
    """Tests for SignedOrder dataclass."""
    
    def test_signed_order_creation(self):
        """Test creating SignedOrder."""
        signed = SignedOrder(
            coin="ETH",
            is_buy=True,
            sz="5.0",
            limit_px="2000.0",
            order_type={"market": {}},
            reduce_only=False,
            signature="0x123abc",
            nonce=123456,
        )
        
        assert signed.coin == "ETH"
        assert signed.signature == "0x123abc"
        assert signed.nonce == 123456
