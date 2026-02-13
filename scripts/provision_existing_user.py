"""
Provision server wallets for an existing user and clean up test wallets.

Operations:
1. Detach policy from test EVM wallet (c8rps4e97bnbpeqyh880btp2)
2. Provision production EVM + Solana server wallets for the existing user
3. Store wallet IDs and addresses in the database

Usage:
    .venv/bin/python3 scripts/provision_existing_user.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.venues.privy_signer import _create_privy_client
from bot.venues.server_wallets import ServerWalletService, ServerWallets
from shared.db.database import Database

# Constants
TEST_WALLET_ID = "c8rps4e97bnbpeqyh880btp2"
EXISTING_USER_ID = "did:privy:cmligjikm002b0cielm5urxjj"


def cleanup_test_wallet(client) -> bool:
    """Detach policies from the test EVM wallet.

    The Privy SDK has no wallet delete method, so we strip
    policies to render the test wallet inert.
    """
    print(f"\n--- Cleanup test wallet {TEST_WALLET_ID} ---")
    try:
        wallet = client.wallets.get(TEST_WALLET_ID)
        print(f"  Found: {wallet.address}")
        client.wallets.update(TEST_WALLET_ID, policy_ids=[])
        print(f"  Detached all policies (wallet is now inert)")
        return True
    except Exception as e:
        err = str(e).lower()
        if "not found" in err or "404" in err:
            print(f"  Not found (already cleaned up)")
            return True
        print(f"  Error: {str(e)[:200]}")
        print(f"  NOTE: SDK has no wallets.delete(). Clean up via Privy dashboard if needed.")
        return False


async def provision_user(db: Database) -> ServerWallets:
    """Provision production server wallets for the existing user."""
    print(f"\n--- Provision wallets for {EXISTING_USER_ID} ---")

    # Verify user exists in DB
    row = await db.fetchone(
        "SELECT id, email, server_evm_wallet_id, server_solana_wallet_id FROM users WHERE id = $1",
        (EXISTING_USER_ID,),
    )
    if not row:
        print(f"  ERROR: User {EXISTING_USER_ID} not found in database")
        sys.exit(1)

    print(f"  User found: {row.get('email')}")

    if row.get("server_evm_wallet_id") and row.get("server_solana_wallet_id"):
        print(f"  Already provisioned:")
        print(f"    EVM wallet: {row['server_evm_wallet_id']}")
        print(f"    Solana wallet: {row['server_solana_wallet_id']}")

        full = await db.fetchone(
            """SELECT server_evm_wallet_id, server_evm_address,
                      server_solana_wallet_id, server_solana_address
               FROM users WHERE id = $1""",
            (EXISTING_USER_ID,),
        )
        return ServerWallets(
            evm_wallet_id=full["server_evm_wallet_id"],
            evm_address=full["server_evm_address"],
            solana_wallet_id=full["server_solana_wallet_id"],
            solana_address=full["server_solana_address"],
        )

    # Provision via the service
    svc = ServerWalletService(db)
    wallets = await svc.ensure_wallets_for_user(EXISTING_USER_ID)

    print(f"  Provisioned:")
    print(f"    EVM: {wallets.evm_wallet_id} ({wallets.evm_address})")
    print(f"    Solana: {wallets.solana_wallet_id} ({wallets.solana_address})")

    return wallets


async def main():
    """Run cleanup and provisioning."""
    # Step 1: Cleanup test wallet
    client = _create_privy_client()
    cleanup_test_wallet(client)

    # Step 2: Provision user
    db = Database()  # Uses default DATABASE_URL
    await db.connect()
    try:
        wallets = await provision_user(db)
    finally:
        await db.close()

    # Summary
    print("\n" + "=" * 60)
    print("PROVISIONING SUMMARY")
    print("=" * 60)
    print(f"  User: {EXISTING_USER_ID}")
    print(f"  EVM wallet:    {wallets.evm_wallet_id}")
    print(f"  EVM address:   {wallets.evm_address}")
    print(f"  Solana wallet: {wallets.solana_wallet_id}")
    print(f"  Solana address: {wallets.solana_address}")
    print(f"  Complete: {wallets.is_complete}")


if __name__ == "__main__":
    asyncio.run(main())
