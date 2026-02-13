"""
Server wallet provisioning service.

Creates and manages per-user Privy server wallets (EVM + Solana).
Each user gets their own pair of wallets, created on first sign-in,
with shared policies attached.

Wallets are:
- Created via Privy API with key quorum for authorization
- Assigned the shared EVM/Solana policies from Phase 1
- Stored in the users table (server_evm_wallet_id, etc.)
- Idempotent: safe to call multiple times for the same user
- Concurrency-safe: pg_advisory_lock prevents duplicate creation

See docs/implementation-plan.md Phase 2.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shared.config.settings import SECRETS_DIR
from shared.config.wallet_policies import KEY_QUORUM_ID
from shared.db.database import Database
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Load policy IDs from secrets
_policy_ids: Optional[dict] = None


def _load_policy_ids() -> dict:
    """Load policy IDs from secrets/policy_ids.json.

    Returns dict with 'evm_policy_id' and 'solana_policy_id'.
    """
    global _policy_ids
    if _policy_ids is None:
        policy_path = SECRETS_DIR / "policy_ids.json"
        if not policy_path.exists():
            raise FileNotFoundError(
                f"Policy IDs not found at {policy_path}. "
                "Run scripts/create_policies.py first."
            )
        _policy_ids = json.loads(policy_path.read_text())
    return _policy_ids


@dataclass
class ServerWallets:
    """A user's server wallet pair."""
    evm_wallet_id: Optional[str] = None
    evm_address: Optional[str] = None
    solana_wallet_id: Optional[str] = None
    solana_address: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        """True if both EVM and Solana wallets are provisioned."""
        return all([
            self.evm_wallet_id,
            self.evm_address,
            self.solana_wallet_id,
            self.solana_address,
        ])

    @property
    def is_partial(self) -> bool:
        """True if at least one wallet exists but not both."""
        has_evm = bool(self.evm_wallet_id)
        has_solana = bool(self.solana_wallet_id)
        return has_evm != has_solana


class ServerWalletService:
    """Provisions and manages per-user Privy server wallets.

    Each user gets an EVM wallet (for HL trading on Arbitrum) and a
    Solana wallet (for Asgard positions). Policies are attached at
    creation time.

    Args:
        db: Database instance for reading/writing user records.
    """

    def __init__(self, db: Database):
        self.db = db
        self._client = None

    @property
    def client(self):
        """Lazy-load the Privy API client."""
        if self._client is None:
            from bot.venues.privy_signer import _create_privy_client
            self._client = _create_privy_client()
        return self._client

    async def get_user_wallets(self, user_id: str) -> ServerWallets:
        """Load a user's server wallets from the database.

        Args:
            user_id: Privy user ID (did:privy:...).

        Returns:
            ServerWallets with whatever wallet info exists (may be empty).
        """
        row = await self.db.fetchone(
            """SELECT server_evm_wallet_id, server_evm_address,
                      server_solana_wallet_id, server_solana_address
               FROM users WHERE id = $1""",
            (user_id,),
        )
        if not row:
            return ServerWallets()
        return ServerWallets(
            evm_wallet_id=row["server_evm_wallet_id"],
            evm_address=row["server_evm_address"],
            solana_wallet_id=row["server_solana_wallet_id"],
            solana_address=row["server_solana_address"],
        )

    async def ensure_wallets_for_user(self, user_id: str) -> ServerWallets:
        """Ensure a user has both server wallets. Idempotent.

        Uses PostgreSQL advisory lock to prevent concurrent provisioning
        for the same user (N1). If wallets already exist, returns them
        immediately without any API calls.

        If one wallet exists but not the other (partial state from a
        previous failure), only the missing wallet is created.

        Args:
            user_id: Privy user ID (did:privy:...).

        Returns:
            ServerWallets with both wallets provisioned.

        Raises:
            Exception: If Privy API calls fail. Partial state is stored
                so the next call will only create the missing wallet.
        """
        # Fast path: check if wallets already exist
        wallets = await self.get_user_wallets(user_id)
        if wallets.is_complete:
            logger.debug("server_wallets_exist", user_id=user_id)
            return wallets

        # Acquire advisory lock to prevent concurrent provisioning.
        # hashtext() converts a string to a 32-bit int suitable for
        # pg_advisory_xact_lock. We use the transaction-scoped variant
        # so the lock is released when the transaction commits/rolls back.
        async with self.db.transaction() as tx:
            await tx.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                (f"provision:{user_id}",),
            )

            # Re-check under lock (another request may have provisioned
            # while we waited for the lock)
            row = await tx.fetchone(
                """SELECT server_evm_wallet_id, server_evm_address,
                          server_solana_wallet_id, server_solana_address
                   FROM users WHERE id = $1""",
                (user_id,),
            )
            if not row:
                logger.error("user_not_found", user_id=user_id)
                raise ValueError(f"User {user_id} not found in database")

            wallets = ServerWallets(
                evm_wallet_id=row["server_evm_wallet_id"],
                evm_address=row["server_evm_address"],
                solana_wallet_id=row["server_solana_wallet_id"],
                solana_address=row["server_solana_address"],
            )

            if wallets.is_complete:
                logger.debug("server_wallets_exist_after_lock", user_id=user_id)
                return wallets

            # Create missing wallets
            if not wallets.evm_wallet_id:
                logger.info("creating_evm_wallet", user_id=user_id)
                evm = self._create_evm_wallet()
                wallets.evm_wallet_id = evm["wallet_id"]
                wallets.evm_address = evm["address"]
                await tx.execute(
                    """UPDATE users
                       SET server_evm_wallet_id = $1, server_evm_address = $2
                       WHERE id = $3""",
                    (wallets.evm_wallet_id, wallets.evm_address, user_id),
                )
                logger.info(
                    "evm_wallet_created",
                    user_id=user_id,
                    wallet_id=wallets.evm_wallet_id,
                    address=wallets.evm_address,
                )

            if not wallets.solana_wallet_id:
                logger.info("creating_solana_wallet", user_id=user_id)
                sol = self._create_solana_wallet()
                wallets.solana_wallet_id = sol["wallet_id"]
                wallets.solana_address = sol["address"]
                await tx.execute(
                    """UPDATE users
                       SET server_solana_wallet_id = $1, server_solana_address = $2
                       WHERE id = $3""",
                    (wallets.solana_wallet_id, wallets.solana_address, user_id),
                )
                logger.info(
                    "solana_wallet_created",
                    user_id=user_id,
                    wallet_id=wallets.solana_wallet_id,
                    address=wallets.solana_address,
                )

        return wallets

    def _create_evm_wallet(self) -> dict:
        """Create an EVM server wallet via Privy API.

        Creates the wallet with the key quorum for signing authorization
        and attaches the EVM policy.

        Returns:
            Dict with 'wallet_id' and 'address'.
        """
        policy_ids = _load_policy_ids()
        evm_policy_id = policy_ids["evm_policy_id"]

        wallet = self.client.wallets.create(chain_type="ethereum")

        # Attach EVM policy
        self.client.wallets.update(
            wallet.id,
            policy_ids=[evm_policy_id],
        )

        logger.info(
            "privy_evm_wallet_created",
            wallet_id=wallet.id,
            address=wallet.address,
            policy_id=evm_policy_id,
        )

        return {"wallet_id": wallet.id, "address": wallet.address}

    def _create_solana_wallet(self) -> dict:
        """Create a Solana server wallet via Privy API.

        Creates the wallet with the key quorum for signing authorization
        and attaches the Solana policy.

        Returns:
            Dict with 'wallet_id' and 'address'.
        """
        policy_ids = _load_policy_ids()
        solana_policy_id = policy_ids.get("solana_policy_id")

        wallet = self.client.wallets.create(chain_type="solana")

        # Attach Solana policy (if available)
        if solana_policy_id:
            self.client.wallets.update(
                wallet.id,
                policy_ids=[solana_policy_id],
            )

        logger.info(
            "privy_solana_wallet_created",
            wallet_id=wallet.id,
            address=wallet.address,
            policy_id=solana_policy_id,
        )

        return {"wallet_id": wallet.id, "address": wallet.address}
