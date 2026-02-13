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
from bot.venues.solana_transferor import SolanaTransferor
from shared.chain.arbitrum import ArbitrumClient
from shared.chain.solana import SolanaClient

logger = logging.getLogger(__name__)


class UserTradingContext:
    """Per-user trading context that holds wallet addresses and IDs.

    Lazily creates trading components configured for that user.
    Server wallet IDs (from Phase 2 provisioning) are passed through
    to the signing layer so that ``wallets.rpc()`` can be called
    without address→ID resolution.
    """

    def __init__(
        self,
        user_id: str,
        solana_address: Optional[str] = None,
        evm_address: Optional[str] = None,
        evm_wallet_id: Optional[str] = None,
        solana_wallet_id: Optional[str] = None,
    ):
        self.user_id = user_id
        self.solana_address = solana_address
        self.evm_address = evm_address
        self.evm_wallet_id = evm_wallet_id
        self.solana_wallet_id = solana_wallet_id

        # Lazily created instances
        self._hl_client: Optional[HyperliquidClient] = None
        self._hl_trader: Optional[HyperliquidTrader] = None
        self._asgard_manager: Optional[AsgardPositionManager] = None
        self._arb_client: Optional[ArbitrumClient] = None
        self._hl_depositor: Optional[HyperliquidDepositor] = None
        self._sol_transferor: Optional[SolanaTransferor] = None
        self._sol_client: Optional[SolanaClient] = None

    @classmethod
    async def from_user_id(cls, user_id: str, db) -> "UserTradingContext":
        """Create a UserTradingContext by loading wallet info from the database.

        Prefers server wallet addresses/IDs (from Phase 2 provisioning).
        Falls back to embedded wallet addresses if server wallets are not
        yet provisioned.

        Args:
            user_id: Privy user ID (matches users.id in DB).
            db: Database instance with fetchone().

        Returns:
            UserTradingContext with resolved wallet addresses.

        Raises:
            ValueError: If user not found or has no wallets.
        """
        user = await db.fetchone(
            """SELECT solana_address, evm_address,
                      server_evm_wallet_id, server_evm_address,
                      server_solana_wallet_id, server_solana_address
               FROM users WHERE id = $1""",
            (user_id,),
        )
        if not user:
            raise ValueError(f"User not found: {user_id}")

        # Prefer server wallet addresses (Phase 2); fall back to embedded
        evm_wallet_id = user.get("server_evm_wallet_id")
        solana_wallet_id = user.get("server_solana_wallet_id")
        evm_address = user.get("server_evm_address") or user.get("evm_address")
        solana_address = user.get("server_solana_address") or user.get("solana_address")

        if not solana_address and not evm_address:
            raise ValueError(f"User {user_id} has no wallet addresses configured")

        return cls(
            user_id=user_id,
            solana_address=solana_address,
            evm_address=evm_address,
            evm_wallet_id=evm_wallet_id,
            solana_wallet_id=solana_wallet_id,
        )

    def get_hl_client(self) -> HyperliquidClient:
        """Get a shared HyperliquidClient (read-only API, no auth needed)."""
        if self._hl_client is None:
            self._hl_client = HyperliquidClient()
        return self._hl_client

    def get_hl_trader(self) -> HyperliquidTrader:
        """Get a HyperliquidTrader configured for this user's EVM wallet.

        The trader's signer will sign transactions using this user's
        server EVM wallet via Privy.
        """
        if self._hl_trader is None:
            client = self.get_hl_client()
            oracle = HyperliquidFundingOracle(client)
            self._hl_trader = HyperliquidTrader(
                client=client,
                oracle=oracle,
                wallet_address=self.evm_address,
                user_id=self.user_id,
                wallet_id=self.evm_wallet_id,
            )
        return self._hl_trader

    def get_asgard_manager(self) -> AsgardPositionManager:
        """Get an AsgardPositionManager configured for this user's Solana wallet.

        The manager's transaction builder will sign transactions using this
        user's server Solana wallet via Privy.
        """
        if self._asgard_manager is None:
            self._asgard_manager = AsgardPositionManager(
                solana_wallet_address=self.solana_address,
                user_id=self.user_id,
                solana_wallet_id=self.solana_wallet_id,
            )
        return self._asgard_manager

    def get_arb_client(self) -> ArbitrumClient:
        """Get a shared ArbitrumClient for RPC reads."""
        if self._arb_client is None:
            self._arb_client = ArbitrumClient()
        return self._arb_client

    def get_hl_depositor(self) -> HyperliquidDepositor:
        """Get a HyperliquidDepositor configured for this user's EVM wallet.

        Bridges USDC from Arbitrum into HL clearinghouse.
        """
        if self._hl_depositor is None:
            self._hl_depositor = HyperliquidDepositor(
                arb_client=self.get_arb_client(),
                wallet_address=self.evm_address,
                user_id=self.user_id,
                hl_trader=self.get_hl_trader(),
                wallet_id=self.evm_wallet_id,
            )
        return self._hl_depositor

    def get_sol_client(self) -> SolanaClient:
        """Get a shared SolanaClient for RPC reads."""
        if self._sol_client is None:
            self._sol_client = SolanaClient()
        return self._sol_client

    def get_solana_transferor(self) -> SolanaTransferor:
        """Get a SolanaTransferor configured for this user's Solana wallet.

        Sends SOL or SPL tokens from the server Solana wallet.
        """
        if self._sol_transferor is None:
            self._sol_transferor = SolanaTransferor(
                sol_client=self.get_sol_client(),
                wallet_address=self.solana_address,
                wallet_id=self.solana_wallet_id,
                user_id=self.user_id,
            )
        return self._sol_transferor

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
        if self._sol_client is not None:
            try:
                await self._sol_client.close()
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
