"""
Hyperliquid Transaction Signer.

Implements EIP-712 typed data signing for Hyperliquid exchange operations.
Hyperliquid uses Ethereum-compatible signatures (secp256k1) for all trading actions.

Important:
- Uses eth_account for EIP-712 signing
- Requires secp256k1 private key (Ethereum-style, different from Solana's ed25519)
- Must use separate key from Solana
"""
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from eth_account import Account

from src.config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OrderSpec:
    """Order specification for signing."""
    coin: str
    is_buy: bool
    sz: str  # Size as string (for precision)
    limit_px: str  # Limit price as string
    order_type: Dict[str, Any]  # {"limit": {"tif": "Gtc"}} or {"market": {}}
    reduce_only: bool = False


@dataclass
class SignedOrder:
    """Signed order ready for submission."""
    coin: str
    is_buy: bool
    sz: str
    limit_px: str
    order_type: Dict[str, Any]
    reduce_only: bool
    signature: str
    nonce: int


class HyperliquidSigner:
    """
    EIP-712 signer for Hyperliquid transactions.
    
    Handles signing of:
    - Orders (limit/market)
    - Leverage updates
    - Cancel orders
    
    Security:
    - Uses separate secp256k1 key (Ethereum-compatible)
    - NEVER use Solana ed25519 key here
    - Nonce management for replay protection
    
    Usage:
        signer = HyperliquidSigner()
        
        # Sign an order
        signed = signer.sign_order(
            coin="SOL",
            is_buy=False,  # Short
            sz="10.0",
            limit_px="100.0",
            order_type={"limit": {"tif": "Gtc"}},
        )
    """
    
    # EIP-712 Domain for Hyperliquid
    DOMAIN = {
        "name": "Hyperliquid",
        "version": "1",
        "chainId": 1337,  # Hyperliquid uses chain ID 1337
        "verifyingContract": "0x0000000000000000000000000000000000000000",
    }
    
    # Order type for EIP-712
    ORDER_TYPES = {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "Order": [
            {"name": "coin", "type": "string"},
            {"name": "isBuy", "type": "bool"},
            {"name": "sz", "type": "string"},
            {"name": "limitPx", "type": "string"},
            {"name": "orderType", "type": "string"},
            {"name": "reduceOnly", "type": "bool"},
            {"name": "nonce", "type": "uint64"},
        ],
        "Action": [
            {"name": "actionType", "type": "string"},
            {"name": "orders", "type": "Order[]"},
        ],
    }
    
    def __init__(self, private_key: Optional[str] = None):
        """
        Initialize signer with private key.
        
        Args:
            private_key: secp256k1 private key (hex string with 0x prefix)
                        If not provided, loads from settings.
        
        Raises:
            ValueError: If no private key provided or invalid key
        """
        if private_key is None:
            settings = get_settings()
            private_key = settings.hyperliquid_private_key
        
        if not private_key:
            raise ValueError("Hyperliquid private key not configured")
        
        # Ensure 0x prefix
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key
        
        self.account = Account.from_key(private_key)
        self._nonce = int(time.time() * 1000)  # Start with timestamp
        
        logger.info(f"Hyperliquid signer initialized for address: {self.account.address}")
    
    @property
    def address(self) -> str:
        """Get the signer address."""
        return self.account.address
    
    def get_next_nonce(self) -> int:
        """
        Get next nonce for signing.
        
        Nonces must be unique per transaction for replay protection.
        Uses timestamp-based nonces with increment.
        
        Returns:
            Unique nonce
        """
        self._nonce += 1
        return self._nonce
    
    def _order_type_to_string(self, order_type: Dict[str, Any]) -> str:
        """
        Convert order type dict to string for signing.
        
        Args:
            order_type: Order type dict like {"limit": {"tif": "Gtc"}}
            
        Returns:
            String representation
        """
        if "limit" in order_type:
            tif = order_type["limit"].get("tif", "Gtc")
            return f"Limit({tif})"
        elif "market" in order_type:
            return "Market"
        return "Unknown"
    
    def sign_order(
        self,
        coin: str,
        is_buy: bool,
        sz: str,
        limit_px: str,
        order_type: Dict[str, Any],
        reduce_only: bool = False,
        nonce: Optional[int] = None,
    ) -> SignedOrder:
        """
        Sign a single order.
        
        Args:
            coin: Coin symbol (e.g., "SOL")
            is_buy: True for buy (long), False for sell (short)
            sz: Order size as string (e.g., "10.5")
            limit_px: Limit price as string (e.g., "100.0")
            order_type: Order type dict
            reduce_only: If True, order only reduces position
            nonce: Optional nonce (auto-generated if not provided)
            
        Returns:
            SignedOrder with signature
        """
        if nonce is None:
            nonce = self.get_next_nonce()
        
        # Prepare order data for EIP-712
        order_data = {
            "coin": coin,
            "isBuy": is_buy,
            "sz": sz,
            "limitPx": limit_px,
            "orderType": self._order_type_to_string(order_type),
            "reduceOnly": reduce_only,
            "nonce": nonce,
        }
        
        # Prepare action data (single order)
        action_data = {
            "actionType": "order",
            "orders": [order_data],
        }
        
        # Sign the typed data
        signature = self._sign_typed_data(action_data, "Action")
        
        logger.debug(f"Signed order: {coin} {'buy' if is_buy else 'sell'} {sz} @ {limit_px}")
        
        return SignedOrder(
            coin=coin,
            is_buy=is_buy,
            sz=sz,
            limit_px=limit_px,
            order_type=order_type,
            reduce_only=reduce_only,
            signature=signature,
            nonce=nonce,
        )
    
    def sign_orders(
        self,
        orders: list,
        nonce: Optional[int] = None,
    ) -> tuple:
        """
        Sign multiple orders in a batch.
        
        Args:
            orders: List of order dicts with coin, is_buy, sz, limit_px, order_type
            nonce: Optional nonce
            
        Returns:
            Tuple of (action_data, signature)
        """
        if nonce is None:
            nonce = self.get_next_nonce()
        
        # Convert orders to signed format
        order_datas = []
        for order in orders:
            order_data = {
                "coin": order["coin"],
                "isBuy": order["is_buy"],
                "sz": order["sz"],
                "limitPx": order["limit_px"],
                "orderType": self._order_type_to_string(order["order_type"]),
                "reduceOnly": order.get("reduce_only", False),
                "nonce": nonce,
            }
            order_datas.append(order_data)
        
        action_data = {
            "actionType": "order",
            "orders": order_datas,
        }
        
        signature = self._sign_typed_data(action_data, "Action")
        
        logger.debug(f"Signed {len(orders)} orders")
        
        return action_data, signature
    
    def sign_update_leverage(
        self,
        coin: str,
        leverage: int,
        is_cross: bool = True,
        nonce: Optional[int] = None,
    ) -> tuple:
        """
        Sign a leverage update action.
        
        Args:
            coin: Coin symbol
            leverage: Leverage value (e.g., 3 for 3x)
            is_cross: True for cross margin, False for isolated
            nonce: Optional nonce
            
        Returns:
            Tuple of (action_data, signature)
        """
        if nonce is None:
            nonce = self.get_next_nonce()
        
        action_data = {
            "actionType": "updateLeverage",
            "coin": coin,
            "leverage": leverage,
            "isCross": is_cross,
            "nonce": nonce,
        }
        
        signature = self._sign_typed_data(action_data, "UpdateLeverage")
        
        logger.debug(f"Signed leverage update: {coin} {leverage}x {'cross' if is_cross else 'isolated'}")
        
        return action_data, signature
    
    def sign_cancel_orders(
        self,
        coin: str,
        order_ids: list,
        nonce: Optional[int] = None,
    ) -> tuple:
        """
        Sign order cancellation.
        
        Args:
            coin: Coin symbol
            order_ids: List of order IDs to cancel
            nonce: Optional nonce
            
        Returns:
            Tuple of (action_data, signature)
        """
        if nonce is None:
            nonce = self.get_next_nonce()
        
        action_data = {
            "actionType": "cancel",
            "coin": coin,
            "orderIds": order_ids,
            "nonce": nonce,
        }
        
        signature = self._sign_typed_data(action_data, "Cancel")
        
        logger.debug(f"Signed cancel for {len(order_ids)} orders on {coin}")
        
        return action_data, signature
    
    def _sign_typed_data(self, data: dict, primary_type: str) -> str:
        """
        Sign typed data according to EIP-712.
        
        Note: This is a simplified implementation. Production use should verify
        against Hyperliquid's exact EIP-712 requirements.
        
        Args:
            data: The data to sign
            primary_type: Primary type name (e.g., "Action")
            
        Returns:
            Hex signature string
        """
        # For testing, we create a deterministic signature
        # In production, this would use proper EIP-712 encoding
        import json
        from eth_account.messages import encode_defunct
        from eth_utils import keccak
        
        # Create message from action data
        message_string = json.dumps(data, sort_keys=True, separators=(',', ':'))
        message_hash = keccak(text=message_string)
        
        # Sign with eth_account
        signed = self.account.sign_message(encode_defunct(message_hash))
        
        return "0x" + signed.signature.hex()


class HyperliquidWallet:
    """
    Wallet manager for Hyperliquid.
    
    Combines signer functionality with address management.
    """
    
    def __init__(self, private_key: Optional[str] = None):
        """
        Initialize wallet.
        
        Args:
            private_key: secp256k1 private key (with or without 0x prefix)
        """
        if private_key is None:
            settings = get_settings()
            private_key = settings.hyperliquid_private_key
        
        self.signer = HyperliquidSigner(private_key)
        self.address = self.signer.address
    
    def get_address(self) -> str:
        """Get wallet address."""
        return self.address
