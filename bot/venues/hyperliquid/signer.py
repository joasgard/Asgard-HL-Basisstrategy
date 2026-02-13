"""
Hyperliquid Transaction Signer via Privy.

Implements the Hyperliquid phantom agent signing pattern:
1. Build action in wire format
2. Compute action hash (msgpack + nonce -> keccak256)
3. Construct phantom agent from hash
4. Sign phantom agent via Privy EIP-712

Reference: https://github.com/hyperliquid-dex/hyperliquid-python-sdk
"""
import struct
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import msgpack
from eth_hash.auto import keccak

from shared.config.settings import get_settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SignedAction:
    """Signed action ready for submission to HL exchange endpoint."""
    action: Dict[str, Any]
    signature: Dict[str, Any]  # {"r": "0x...", "s": "0x...", "v": 27|28}
    nonce: int


class HyperliquidSigner:
    """
    EIP-712 signer for Hyperliquid using the phantom agent pattern.

    All signing operations are delegated to Privy's secure infrastructure.
    No private keys are stored or used locally.

    How Hyperliquid signing works:
    1. The action dict is msgpack-encoded, combined with nonce and vault info
    2. A keccak256 hash is computed over the encoded bytes
    3. A "phantom agent" struct is created: {source: "a", connectionId: hash}
    4. The phantom agent is signed via EIP-712 (domain: "Exchange", chainId: 1337)
    5. The original action + signature are submitted to /exchange

    User-signed actions (usdClassTransfer, withdraw, etc.) use a different
    domain ("HyperliquidSignTransaction", chainId: 42161) and sign the action
    data directly without the phantom agent pattern.
    """

    # EIP-712 domain for L1 actions (orders, leverage, cancels)
    DOMAIN = {
        "name": "Exchange",
        "version": "1",
        "chainId": 1337,
        "verifyingContract": "0x0000000000000000000000000000000000000000",
    }

    # EIP-712 types for phantom agent signing
    AGENT_TYPES = {
        "Agent": [
            {"name": "source", "type": "string"},
            {"name": "connectionId", "type": "bytes32"},
        ],
    }

    # EIP-712 domain for user-signed actions (usdClassTransfer, etc.)
    USER_SIGNED_DOMAIN = {
        "name": "HyperliquidSignTransaction",
        "version": "1",
        "chainId": 42161,
        "verifyingContract": "0x0000000000000000000000000000000000000000",
    }

    def __init__(
        self,
        wallet_address: str = None,
        user_id: str = None,
        wallet_id: str = None,
    ):
        """Initialize signer with Privy wallet signer.

        Args:
            wallet_address: EVM wallet address to sign with.
            user_id: Optional user ID for multi-tenant mode.
            wallet_id: Privy wallet ID (from server wallets DB).
        """
        from bot.venues.privy_signer import PrivyWalletSigner

        settings = get_settings()

        self.wallet_address = wallet_address or settings.wallet_address
        self.user_id = user_id
        self._privy_signer = PrivyWalletSigner(
            wallet_id=wallet_id,
            wallet_address=self.wallet_address,
            user_id=user_id,
        )

        logger.info(
            "hl_signer_initialized",
            address=self.wallet_address,
            wallet_id=wallet_id,
            user_id=user_id,
        )

    @property
    def address(self) -> str:
        """Get the signer address."""
        return self.wallet_address

    # ------------------------------------------------------------------
    # Core signing
    # ------------------------------------------------------------------

    def _action_hash(
        self,
        action: dict,
        vault_address: Optional[str],
        nonce: int,
    ) -> bytes:
        """
        Compute action hash matching the Hyperliquid SDK.

        The hash is: keccak256(msgpack(action) || nonce_be_u64 || vault_flag)
        """
        buf = msgpack.packb(action)
        buf += struct.pack(">Q", nonce)
        if vault_address is None:
            buf += b"\x00"
        else:
            buf += b"\x01" + bytes.fromhex(vault_address[2:])
        return keccak(buf)

    def _construct_phantom_agent(self, hash_bytes: bytes) -> dict:
        """Construct phantom agent from action hash (mainnet)."""
        return {
            "source": "a",
            "connectionId": hash_bytes,
        }

    def _parse_signature(self, raw_sig) -> Dict[str, Any]:
        """
        Parse a signature into {r, s, v} format for HL exchange endpoint.

        Handles both hex string signatures and dict signatures.
        """
        if isinstance(raw_sig, dict):
            return raw_sig

        # Hex string signature: strip 0x prefix, decode 65 bytes (r[32]+s[32]+v[1])
        sig_hex = raw_sig
        if sig_hex.startswith("0x"):
            sig_hex = sig_hex[2:]

        sig_bytes = bytes.fromhex(sig_hex)

        r = "0x" + sig_bytes[:32].hex()
        s = "0x" + sig_bytes[32:64].hex()
        v = sig_bytes[64]

        # Normalize v value (some signers return 0/1 instead of 27/28)
        if v < 27:
            v += 27

        return {"r": r, "s": s, "v": v}

    async def sign_l1_action(
        self,
        action: dict,
        vault_address: Optional[str] = None,
        nonce: Optional[int] = None,
    ) -> SignedAction:
        """
        Sign an L1 action using the phantom agent pattern.

        This is the core signing method used for orders, leverage updates,
        and other exchange actions.

        Args:
            action: The action dict in HL wire format
            vault_address: Optional vault address (None for personal trading)
            nonce: Timestamp in ms (auto-generated if None)

        Returns:
            SignedAction with action, parsed signature, and nonce
        """
        if nonce is None:
            nonce = int(time.time() * 1000)

        # 1. Compute action hash
        hash_bytes = self._action_hash(action, vault_address, nonce)

        # 2. Construct phantom agent
        phantom_agent = self._construct_phantom_agent(hash_bytes)

        # 3. Sign phantom agent via Privy EIP-712
        raw_signature = self._privy_signer.sign_typed_data_v4(
            domain=self.DOMAIN,
            types=self.AGENT_TYPES,
            value=phantom_agent,
            primary_type="Agent",
        )

        # 4. Parse signature into {r, s, v}
        signature = self._parse_signature(raw_signature)

        logger.debug(f"Signed L1 action: type={action.get('type')}")

        return SignedAction(action=action, signature=signature, nonce=nonce)

    async def sign_user_action(
        self,
        action: dict,
        types: dict,
        primary_type: str,
        value: dict,
        nonce: Optional[int] = None,
    ) -> SignedAction:
        """
        Sign a user-signed action (usdClassTransfer, withdraw, etc.).

        These use a different EIP-712 domain and sign the action data
        directly (no phantom agent).

        Args:
            action: Full action dict for the exchange endpoint
            types: EIP-712 types for this action
            primary_type: EIP-712 primary type name
            value: The struct to sign
            nonce: Timestamp in ms (auto-generated if None)

        Returns:
            SignedAction with action, parsed signature, and nonce
        """
        if nonce is None:
            nonce = int(time.time() * 1000)

        raw_signature = self._privy_signer.sign_typed_data_v4(
            domain=self.USER_SIGNED_DOMAIN,
            types=types,
            value=value,
            primary_type=primary_type,
        )

        signature = self._parse_signature(raw_signature)

        logger.debug(f"Signed user action: type={action.get('type')}")

        return SignedAction(action=action, signature=signature, nonce=nonce)

    # ------------------------------------------------------------------
    # High-level signing methods
    # ------------------------------------------------------------------

    async def sign_order(
        self,
        asset_index: int,
        is_buy: bool,
        sz: str,
        limit_px: str,
        order_type: Dict[str, Any],
        reduce_only: bool = False,
        nonce: Optional[int] = None,
    ) -> SignedAction:
        """
        Sign an order action.

        Args:
            asset_index: Numeric asset index from HL universe (e.g. SOL=4)
            is_buy: True for buy, False for sell
            sz: Size as string
            limit_px: Limit price as string
            order_type: Order type dict, e.g. {"limit": {"tif": "Ioc"}}
            reduce_only: Whether order is reduce-only
            nonce: Optional nonce override

        Returns:
            SignedAction ready for exchange endpoint submission
        """
        order_wire = {
            "a": asset_index,
            "b": is_buy,
            "p": limit_px,
            "s": sz,
            "r": reduce_only,
            "t": order_type,
        }

        action = {
            "type": "order",
            "orders": [order_wire],
            "grouping": "na",
        }

        logger.debug(
            f"Signing order: asset={asset_index} "
            f"{'buy' if is_buy else 'sell'} {sz} @ {limit_px}"
        )

        return await self.sign_l1_action(action, nonce=nonce)

    async def sign_leverage_update(
        self,
        asset_index: int,
        leverage: int,
        is_cross: bool = True,
        nonce: Optional[int] = None,
    ) -> SignedAction:
        """
        Sign a leverage update action.

        Args:
            asset_index: Numeric asset index
            leverage: Leverage value (1-50)
            is_cross: True for cross margin, False for isolated

        Returns:
            SignedAction ready for exchange endpoint submission
        """
        action = {
            "type": "updateLeverage",
            "asset": asset_index,
            "isCross": is_cross,
            "leverage": leverage,
        }

        logger.debug(
            f"Signing leverage update: asset={asset_index} "
            f"{leverage}x {'cross' if is_cross else 'isolated'}"
        )

        return await self.sign_l1_action(action, nonce=nonce)

    async def sign_usd_class_transfer(
        self,
        amount: str,
        to_perp: bool,
        nonce: Optional[int] = None,
    ) -> SignedAction:
        """
        Sign a spot<->perp USDC transfer (user-signed action).

        Args:
            amount: USDC amount as string (human-readable, e.g. "1000.0")
            to_perp: True = spot->perp, False = perp->spot

        Returns:
            SignedAction ready for exchange endpoint submission
        """
        if nonce is None:
            nonce = int(time.time() * 1000)

        action = {
            "type": "usdClassTransfer",
            "hyperliquidChain": "Mainnet",
            "signatureChainId": "0xa4b1",
            "amount": amount,
            "toPerp": to_perp,
            "nonce": nonce,
        }

        types = {
            "HyperliquidTransaction:UsdClassTransfer": [
                {"name": "hyperliquidChain", "type": "string"},
                {"name": "amount", "type": "string"},
                {"name": "toPerp", "type": "bool"},
                {"name": "nonce", "type": "uint64"},
            ],
        }

        value = {
            "hyperliquidChain": "Mainnet",
            "amount": amount,
            "toPerp": to_perp,
            "nonce": nonce,
        }

        logger.info(
            f"Signing usdClassTransfer: {amount} USDC "
            f"{'spot->perp' if to_perp else 'perp->spot'}"
        )

        return await self.sign_user_action(
            action=action,
            types=types,
            primary_type="HyperliquidTransaction:UsdClassTransfer",
            value=value,
            nonce=nonce,
        )
