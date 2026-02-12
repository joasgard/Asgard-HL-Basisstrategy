"""
Per-user trading context for multi-tenant SaaS mode.

Creates user-specific instances of HyperliquidTrader and AsgardPositionManager
using the user's own wallet addresses (resolved from the database).

Privy app credentials are shared (they belong to the app), but each user's
embedded wallet address is different. Privy signs on behalf of whichever
wallet address is specified.

Usage:
    # From user_id (loads wallets from DB)
    ctx = await UserTradingContext.from_user_id("did:privy:abc123", db)

    # Or with known addresses
    ctx = UserTradingContext(
        user_id="did:privy:abc123",
        solana_address="SoL...",
        evm_address="0x...",
    )

    # Get per-user trading components
    hl_trader = ctx.get_hl_trader()
    asgard_mgr = ctx.get_asgard_manager()
"""
import logging
from typing import Optional

from bot.venues.asgard.manager import AsgardPositionManager
from bot.venues.hyperliquid.client import HyperliquidClient
from bot.venues.hyperliquid.depositor import HyperliquidDepositor
from bot.venues.hyperliquid.funding_oracle import HyperliquidFundingOracle
from bot.venues.hyperliquid.signer import HyperliquidSigner
from bot.venues.hyperliquid.trader import HyperliquidTrader
from shared.chain.arbitrum import ArbitrumClient

logger = logging.getLogger(__name__)


class UserTradingContext:
    """
    Per-user trading context that holds wallet addresses and lazily
    creates trading components configured for that user.
    """

    def __init__(
        self,
        user_id: str,
        solana_address: Optional[str] = None,
        evm_address: Optional[str] = None,
    ):
        self.user_id = user_id
        self.solana_address = solana_address
        self.evm_address = evm_address

        # Lazily created instances
        self._hl_client: Optional[HyperliquidClient] = None
        self._hl_trader: Optional[HyperliquidTrader] = None
        self._asgard_manager: Optional[AsgardPositionManager] = None
        self._arb_client: Optional[ArbitrumClient] = None
        self._hl_depositor: Optional[HyperliquidDepositor] = None

    @classmethod
    async def from_user_id(cls, user_id: str, db) -> "UserTradingContext":
        """
        Create a UserTradingContext by loading wallet addresses from the database.

        Args:
            user_id: Privy user ID (matches users.id in DB)
            db: Database instance with fetchone()

        Returns:
            UserTradingContext with resolved wallet addresses

        Raises:
            ValueError: If user not found or has no wallets
        """
        user = await db.fetchone(
            "SELECT solana_address, evm_address FROM users WHERE id = ?",
            (user_id,)
        )
        if not user:
            raise ValueError(f"User not found: {user_id}")

        solana_address = user.get("solana_address") or user.get("solana_address")
        evm_address = user.get("evm_address") or user.get("evm_address")

        if not solana_address and not evm_address:
            raise ValueError(f"User {user_id} has no wallet addresses configured")

        return cls(
            user_id=user_id,
            solana_address=solana_address,
            evm_address=evm_address,
        )

    def get_hl_client(self) -> HyperliquidClient:
        """Get a shared HyperliquidClient (read-only API, no auth needed)."""
        if self._hl_client is None:
            self._hl_client = HyperliquidClient()
        return self._hl_client

    def get_hl_trader(self) -> HyperliquidTrader:
        """
        Get a HyperliquidTrader configured for this user's EVM wallet.

        The trader's signer will sign transactions using this user's
        embedded EVM wallet via Privy.
        """
        if self._hl_trader is None:
            client = self.get_hl_client()
            oracle = HyperliquidFundingOracle(client)
            self._hl_trader = HyperliquidTrader(
                client=client,
                oracle=oracle,
                wallet_address=self.evm_address,
                user_id=self.user_id,
            )
        return self._hl_trader

    def get_asgard_manager(self) -> AsgardPositionManager:
        """
        Get an AsgardPositionManager configured for this user's Solana wallet.

        The manager's transaction builder will sign transactions using this
        user's embedded Solana wallet via Privy.
        """
        if self._asgard_manager is None:
            self._asgard_manager = AsgardPositionManager(
                solana_wallet_address=self.solana_address,
                user_id=self.user_id,
            )
        return self._asgard_manager

    def get_arb_client(self) -> ArbitrumClient:
        """Get a shared ArbitrumClient for RPC reads."""
        if self._arb_client is None:
            self._arb_client = ArbitrumClient()
        return self._arb_client

    def get_hl_depositor(self) -> HyperliquidDepositor:
        """
        Get a HyperliquidDepositor configured for this user's EVM wallet.

        Bridges USDC from Arbitrum into HL clearinghouse.
        """
        if self._hl_depositor is None:
            self._hl_depositor = HyperliquidDepositor(
                arb_client=self.get_arb_client(),
                wallet_address=self.evm_address,
                user_id=self.user_id,
                hl_trader=self.get_hl_trader(),
            )
        return self._hl_depositor

    async def close(self):
        """Clean up HTTP sessions."""
        if self._hl_trader is not None:
            try:
                await self._hl_trader.__aexit__(None, None, None)
            except Exception:
                pass
        if self._asgard_manager is not None:
            try:
                await self._asgard_manager.__aexit__(None, None, None)
            except Exception:
                pass
        if self._arb_client is not None:
            try:
                await self._arb_client.close()
            except Exception:
                pass

    async def __aenter__(self) -> "UserTradingContext":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def __repr__(self) -> str:
        return (
            f"UserTradingContext(user_id={self.user_id!r}, "
            f"sol={self.solana_address[:8] + '...' if self.solana_address else None}, "
            f"evm={self.evm_address[:8] + '...' if self.evm_address else None})"
        )
