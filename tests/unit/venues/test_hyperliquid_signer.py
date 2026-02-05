"""
Tests for Hyperliquid Signer.

These tests verify:
- Signer initialization
- Order signing
- Leverage update signing
- Cancel order signing
- Nonce management
"""
from unittest.mock import MagicMock, patch

import pytest

from src.venues.hyperliquid.signer import (
    HyperliquidSigner,
    HyperliquidWallet,
    SignedOrder,
    OrderSpec,
)


# Test private key (do not use in production - this is a well-known test key)
TEST_PRIVATE_KEY = "0x" + "11" * 32  # 64 hex chars


class TestHyperliquidSignerInit:
    """Tests for signer initialization."""
    
    def test_init_with_explicit_key(self):
        """Test initialization with explicit private key."""
        # Use a valid 32-byte private key
        valid_key = "0x" + "a" * 64
        signer = HyperliquidSigner(private_key=valid_key)
        assert signer.account is not None
        assert signer.address.startswith("0x")
    
    @patch("src.venues.hyperliquid.signer.get_settings")
    def test_init_loads_from_settings(self, mock_get_settings):
        """Test that key is loaded from settings if not provided."""
        mock_settings = MagicMock()
        mock_settings.hyperliquid_private_key = "0x" + "b" * 64
        mock_get_settings.return_value = mock_settings
        
        signer = HyperliquidSigner()
        
        assert signer.account is not None
        mock_get_settings.assert_called_once()
    
    @patch("src.venues.hyperliquid.signer.get_settings")
    def test_init_raises_if_no_key(self, mock_get_settings):
        """Test that error is raised if no key provided."""
        mock_settings = MagicMock()
        mock_settings.hyperliquid_private_key = ""
        mock_get_settings.return_value = mock_settings
        
        with pytest.raises(ValueError, match="Hyperliquid private key not configured"):
            HyperliquidSigner()
    
    def test_init_adds_0x_prefix(self):
        """Test that 0x prefix is added if missing."""
        key_without_prefix = "c" * 64
        signer = HyperliquidSigner(private_key=key_without_prefix)
        assert signer.account is not None


class TestNonceManagement:
    """Tests for nonce management."""
    
    def test_nonce_increments(self):
        """Test that nonces increment."""
        signer = HyperliquidSigner(private_key="0x" + "d" * 64)
        
        nonce1 = signer.get_next_nonce()
        nonce2 = signer.get_next_nonce()
        nonce3 = signer.get_next_nonce()
        
        assert nonce2 == nonce1 + 1
        assert nonce3 == nonce2 + 1
    
    def test_nonce_starts_from_timestamp(self):
        """Test that nonce starts from timestamp."""
        import time
        
        before = int(time.time() * 1000)
        signer = HyperliquidSigner(private_key="0x" + "e" * 64)
        after = int(time.time() * 1000)
        
        # Nonce should be around current timestamp
        first_nonce = signer.get_next_nonce()
        assert before <= first_nonce <= after + 1


class TestOrderSigning:
    """Tests for order signing."""
    
    def test_sign_order(self):
        """Test signing a single order."""
        # Use a valid private key (must be < secp256k1 curve order)
        # This is a test key - don't use in production
        signer = HyperliquidSigner(private_key="0x" + "a" * 63 + "1")
        
        signed = signer.sign_order(
            coin="SOL",
            is_buy=False,
            sz="10.5",
            limit_px="100.0",
            order_type={"limit": {"tif": "Gtc"}},
            reduce_only=False,
        )
        
        assert isinstance(signed, SignedOrder)
        assert signed.coin == "SOL"
        assert signed.is_buy is False
        assert signed.sz == "10.5"
        assert signed.limit_px == "100.0"
        assert signed.signature is not None
        assert signed.signature.startswith("0x")
        assert signed.nonce > 0
    
    def test_sign_order_with_nonce(self):
        """Test signing with explicit nonce."""
        signer = HyperliquidSigner(private_key="0x" + "1" * 64)
        
        custom_nonce = 123456789
        signed = signer.sign_order(
            coin="ETH",
            is_buy=True,
            sz="5.0",
            limit_px="2000.0",
            order_type={"market": {}},
            nonce=custom_nonce,
        )
        
        assert signed.nonce == custom_nonce
    
    def test_sign_order_market_type(self):
        """Test signing a market order."""
        signer = HyperliquidSigner(private_key="0x" + "2" * 64)
        
        signed = signer.sign_order(
            coin="SOL",
            is_buy=True,
            sz="1.0",
            limit_px="0",  # Market orders may use 0 for price
            order_type={"market": {}},
        )
        
        assert signed.order_type == {"market": {}}
    
    def test_sign_order_reduce_only(self):
        """Test signing a reduce-only order."""
        signer = HyperliquidSigner(private_key="0x" + "3" * 64)
        
        signed = signer.sign_order(
            coin="SOL",
            is_buy=False,
            sz="5.0",
            limit_px="100.0",
            order_type={"limit": {"tif": "Gtc"}},
            reduce_only=True,
        )
        
        assert signed.reduce_only is True


class TestSignOrders:
    """Tests for batch order signing."""
    
    def test_sign_multiple_orders(self):
        """Test signing multiple orders."""
        signer = HyperliquidSigner(private_key="0x" + "4" * 64)
        
        orders = [
            {
                "coin": "SOL",
                "is_buy": False,
                "sz": "10.0",
                "limit_px": "100.0",
                "order_type": {"limit": {"tif": "Gtc"}},
            },
            {
                "coin": "ETH",
                "is_buy": True,
                "sz": "2.0",
                "limit_px": "2000.0",
                "order_type": {"limit": {"tif": "Gtc"}},
            },
        ]
        
        action_data, signature = signer.sign_orders(orders)
        
        assert action_data["actionType"] == "order"
        assert len(action_data["orders"]) == 2
        assert signature is not None
        assert signature.startswith("0x")


class TestSignUpdateLeverage:
    """Tests for leverage update signing."""
    
    def test_sign_update_leverage(self):
        """Test signing leverage update."""
        signer = HyperliquidSigner(private_key="0x" + "5" * 64)
        
        action_data, signature = signer.sign_update_leverage(
            coin="SOL",
            leverage=5,
            is_cross=True,
        )
        
        assert action_data["actionType"] == "updateLeverage"
        assert action_data["coin"] == "SOL"
        assert action_data["leverage"] == 5
        assert action_data["isCross"] is True
        assert signature is not None
    
    def test_sign_update_leverage_isolated(self):
        """Test signing isolated margin leverage update."""
        signer = HyperliquidSigner(private_key="0x" + "6" * 64)
        
        action_data, signature = signer.sign_update_leverage(
            coin="ETH",
            leverage=10,
            is_cross=False,
        )
        
        assert action_data["isCross"] is False


class TestSignCancelOrders:
    """Tests for order cancellation signing."""
    
    def test_sign_cancel_orders(self):
        """Test signing order cancellation."""
        signer = HyperliquidSigner(private_key="0x" + "7" * 64)
        
        order_ids = ["order123", "order456"]
        action_data, signature = signer.sign_cancel_orders(
            coin="SOL",
            order_ids=order_ids,
        )
        
        assert action_data["actionType"] == "cancel"
        assert action_data["coin"] == "SOL"
        assert action_data["orderIds"] == order_ids
        assert signature is not None
    
    def test_sign_cancel_single_order(self):
        """Test cancelling a single order."""
        signer = HyperliquidSigner(private_key="0x" + "8" * 64)
        
        action_data, signature = signer.sign_cancel_orders(
            coin="ETH",
            order_ids=["order789"],
        )
        
        assert len(action_data["orderIds"]) == 1


class TestHyperliquidWallet:
    """Tests for HyperliquidWallet."""
    
    def test_wallet_init(self):
        """Test wallet initialization."""
        wallet = HyperliquidWallet(private_key="0x" + "9" * 64)
        
        assert wallet.signer is not None
        assert wallet.address.startswith("0x")
    
    def test_wallet_get_address(self):
        """Test getting wallet address."""
        wallet = HyperliquidWallet(private_key="0x" + "a" * 64)
        
        address = wallet.get_address()
        assert address.startswith("0x")
        assert address == wallet.address


class TestOrderSpec:
    """Tests for OrderSpec dataclass."""
    
    def test_order_spec_creation(self):
        """Test creating OrderSpec."""
        spec = OrderSpec(
            coin="SOL",
            is_buy=False,
            sz="10.0",
            limit_px="100.0",
            order_type={"limit": {"tif": "Gtc"}},
            reduce_only=True,
        )
        
        assert spec.coin == "SOL"
        assert spec.is_buy is False
        assert spec.sz == "10.0"
        assert spec.reduce_only is True


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
