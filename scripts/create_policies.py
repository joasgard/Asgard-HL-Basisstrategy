"""
Create Privy wallet policies for server wallets.

Creates both EVM and Solana policies using the rules from
shared/config/wallet_policies.py and stores the policy IDs
in secrets/policy_ids.json.

Usage:
    .venv/bin/python3 scripts/create_policies.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.venues.privy_signer import _create_privy_client
from shared.config.wallet_policies import (
    KEY_QUORUM_ID,
    build_evm_policy_rules,
    build_solana_policy_rules,
)

SECRETS_DIR = Path(__file__).parent.parent / "secrets"
POLICY_IDS_PATH = SECRETS_DIR / "policy_ids.json"


def load_existing_policy_ids() -> dict:
    """Load existing policy IDs if file exists."""
    if POLICY_IDS_PATH.exists():
        return json.loads(POLICY_IDS_PATH.read_text())
    return {}


def save_policy_ids(policy_ids: dict) -> None:
    """Save policy IDs to secrets/policy_ids.json."""
    POLICY_IDS_PATH.write_text(json.dumps(policy_ids, indent=2) + "\n")
    print(f"Saved policy IDs to {POLICY_IDS_PATH}")


def create_evm_policy(client) -> str:
    """Create the EVM policy with all rules.

    Returns the policy ID.
    """
    rules = build_evm_policy_rules()
    print(f"Creating EVM policy with {len(rules)} rules...")
    for r in rules:
        print(f"  {r['action']:5s} {r['method']:30s} {r['name']}")

    policy = client.policies.create(
        chain_type="ethereum",
        name="basis_evm_server_wallet",
        rules=rules,
        version="1.0",
        owner_id=KEY_QUORUM_ID,
    )

    print(f"\nEVM policy created: {policy.id}")
    print(f"  Name: {policy.name}")
    print(f"  Rules: {len(policy.rules)}")
    for r in policy.rules:
        print(f"    [{r.id}] {r.action:5s} {r.method} '{r.name}'")
    return policy.id


def create_solana_policy(client) -> str:
    """Create the Solana policy with all rules.

    The Privy SDK types chain_type as Literal["ethereum"] only, but the
    API supports "solana" for Solana wallet policies. We pass it as a
    string override via extra_body.

    Returns the policy ID.
    """
    rules = build_solana_policy_rules()
    print(f"\nCreating Solana policy with {len(rules)} rules...")
    for r in rules:
        print(f"  {r['action']:5s} {r['method']:30s} {r['name']}")

    # The SDK type hint restricts chain_type to "ethereum", but the API
    # accepts "solana". Use extra_body to override if direct param fails.
    try:
        policy = client.policies.create(
            chain_type="solana",  # type: ignore[arg-type]
            name="basis_solana_server_wallet",
            rules=rules,
            version="1.0",
            owner_id=KEY_QUORUM_ID,
        )
    except Exception as e:
        error_str = str(e)
        if "chain_type" in error_str.lower() or "validation" in error_str.lower():
            print(f"  Direct chain_type='solana' failed: {error_str[:100]}")
            print("  Trying via extra_body override...")
            policy = client.policies.create(
                chain_type="ethereum",  # Will be overridden
                name="basis_solana_server_wallet",
                rules=rules,
                version="1.0",
                owner_id=KEY_QUORUM_ID,
                extra_body={"chain_type": "solana"},
            )
        else:
            raise

    print(f"\nSolana policy created: {policy.id}")
    print(f"  Name: {policy.name}")
    print(f"  Chain type: {policy.chain_type}")
    print(f"  Rules: {len(policy.rules)}")
    for r in policy.rules:
        print(f"    [{r.id}] {r.action:5s} {r.method} '{r.name}'")
    return policy.id


def main():
    """Create EVM and Solana policies and store their IDs."""
    existing = load_existing_policy_ids()
    if existing:
        print(f"Existing policy IDs found: {existing}")
        print("Delete secrets/policy_ids.json to recreate policies.")
        print("Or pass --force to overwrite.")
        if "--force" not in sys.argv:
            return

    client = _create_privy_client()

    print("=== Creating Privy Wallet Policies ===\n")
    print(f"Key quorum: {KEY_QUORUM_ID}")
    print()

    policy_ids = {}

    # EVM policy
    evm_policy_id = create_evm_policy(client)
    policy_ids["evm_policy_id"] = evm_policy_id

    # Solana policy
    try:
        solana_policy_id = create_solana_policy(client)
        policy_ids["solana_policy_id"] = solana_policy_id
    except Exception as e:
        print(f"\nWARNING: Solana policy creation failed: {e}")
        print("This may be due to SDK/API limitations. Storing EVM policy only.")
        policy_ids["solana_policy_id"] = None
        policy_ids["solana_policy_error"] = str(e)[:200]

    # Save
    save_policy_ids(policy_ids)

    print("\n=== Summary ===")
    print(f"EVM policy:    {policy_ids.get('evm_policy_id', 'FAILED')}")
    print(f"Solana policy: {policy_ids.get('solana_policy_id', 'FAILED')}")

    # Verify by fetching back
    print("\n=== Verification ===")
    if evm_policy_id:
        verified = client.policies.get(evm_policy_id)
        print(f"EVM policy verified: {verified.id} ({verified.name}, {len(verified.rules)} rules)")

    if policy_ids.get("solana_policy_id"):
        verified = client.policies.get(policy_ids["solana_policy_id"])
        print(f"Solana policy verified: {verified.id} ({verified.name}, {len(verified.rules)} rules)")


if __name__ == "__main__":
    main()
