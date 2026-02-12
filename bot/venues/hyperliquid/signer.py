"""
Hyperliquid Transaction Signer via Privy.

Delegates all signing operations to Privy's secure infrastructure.
"""
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from shared.config.settings import get_settings

# Lazy import PrivyClient to allow mocking in tests
PrivyClient = None
from shared.utils.logger import get_logger

logger = get_logger(__name__)


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


@dataclass
class SignedSpotTransfer:
    """Signed spot-to-perp transfer ready for submission."""
    usdc_amount: str
    signature: str
    nonce: int


class HyperliquidSigner:
    """
    EIP-712 signer for Hyperliquid transactions via Privy.

    All signing operations are delegated to Privy's secure infrastructure.
    No private keys are stored or used locally.

    Supports per-user wallet addresses for multi-tenant SaaS mode.
    Privy app credentials are shared (they belong to the app, not the user),
    but wallet_address determines which embedded wallet signs the transaction.
    """

    DOMAIN = {
        "name": "Hyperliquid",
        "version": "1",
        "chainId": 1337,
        "verifyingContract": "0x0000000000000000000000000000000000000000",
    }

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
        "SpotTransfer": [
            {"name": "token", "type": "string"},
            {"name": "amount", "type": "string"},
            {"name": "destination", "type": "address"},
        ],
    }

    def __init__(self, wallet_address: str = None, user_id: str = None):
        """
        Initialize signer with Privy client.

        Args:
            wallet_address: EVM wallet address to sign with. If None, falls back
                           to settings.wallet_address for backward compatibility.
            user_id: Optional user ID for logging/debugging in multi-tenant mode.
        """
        # Local import to allow mocking in tests
        from privy import PrivyClient

        settings = get_settings()

        self.privy = PrivyClient(
            app_id=settings.privy_app_id,
            app_secret=settings.privy_app_secret,
            authorization_private_key_path=settings.privy_auth_key_path
        )
        self.wallet_address = wallet_address or settings.wallet_address
        self.user_id = user_id
        # Use time in ms + random suffix to avoid collisions across processes
        self._nonce = int(time.time() * 1000) * 1000 + int.from_bytes(os.urandom(2), "big") % 1000

        logger.info(f"Hyperliquid signer initialized for address: {self.wallet_address}"
                     f"{f' (user: {self.user_id})' if self.user_id else ''}")
    
    @property
    def address(self) -> str:
        """Get the signer address."""
        return self.wallet_address
    
    def get_next_nonce(self) -> int:
        """Get next nonce for signing."""
        self._nonce += 1
        return self._nonce
    
    async def sign_order(
        self,
        coin: str,
        is_buy: bool,
        sz: str,
        limit_px: str,
        order_type: Dict[str, Any],
        reduce_only: bool = False,
        nonce: Optional[int] = None,
    ) -> SignedOrder:
        """Sign order via Privy API."""
        if nonce is None:
            nonce = self.get_next_nonce()
        
        # Build order data
        order_data = {
            "coin": coin,
            "isBuy": is_buy,
            "sz": sz,
            "limitPx": limit_px,
            "orderType": self._order_type_to_string(order_type),
            "reduceOnly": reduce_only,
            "nonce": nonce,
        }
        
        action_data = {
            "actionType": "order",
            "orders": [order_data],
        }
        
        # Sign via Privy
        signature = await self.privy.wallet.sign_typed_data(
            wallet_address=self.wallet_address,
            domain=self.DOMAIN,
            types=self.ORDER_TYPES,
            value=action_data,
            primary_type="Action"
        )
        
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
    
    async def sign_spot_transfer(
        self,
        usdc_amount: str,
        nonce: Optional[int] = None,
    ) -> SignedSpotTransfer:
        """
        Sign an internal spot-to-perp USDC transfer on Hyperliquid.

        This is NOT an Arbitrum bridge deposit. It transfers USDC from
        HL spot balance to HL perp clearinghouse.

        Args:
            usdc_amount: Amount of USDC to transfer (in raw units, 6 decimals)
            nonce: Optional nonce override

        Returns:
            SignedSpotTransfer with signature
        """
        if nonce is None:
            nonce = self.get_next_nonce()
        
        # Build deposit data
        action_data = {
            "actionType": "spotTransfer",
            "transfer": {
                "token": "USDC",
                "amount": usdc_amount,
                "destination": self.wallet_address,  # Transfer to self (spot -> perp)
            },
        }
        
        # Sign via Privy
        signature = await self.privy.wallet.sign_typed_data(
            wallet_address=self.wallet_address,
            domain=self.DOMAIN,
            types=self.ORDER_TYPES,
            value=action_data,
            primary_type="Action"
        )
        
        logger.info(f"Signed spot transfer: {usdc_amount} USDC (spot → perp)")
        
        return SignedSpotTransfer(
            usdc_amount=usdc_amount,
            signature=signature,
            nonce=nonce,
        )
    
    def _order_type_to_string(self, order_type: Dict[str, Any]) -> str:
        """Convert order type dict to string."""
        if "limit" in order_type:
            tif = order_type["limit"].get("tif", "Gtc")
            return f"Limit({tif})"
        elif "market" in order_type:
            return "Market"
        return "Unknown"
