"""
Verify Privy wallet policies and test enforcement.

Tests both EVM and Solana policies by:
1. Verifying policy rules via API query
2. Creating temp wallets with policies attached
3. Testing allowed actions (should succeed)
4. Testing disallowed actions (should be denied)

Usage:
    .venv/bin/python3 scripts/verify_policies.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.venues.privy_signer import _create_privy_client
from shared.config.wallet_policies import (
    HL_BRIDGE_CONTRACT,
    USDC_ARBITRUM,
    HL_EXCHANGE_DOMAIN_CHAIN_ID,
    HL_USER_ACTION_DOMAIN_CHAIN_ID,
)

SECRETS_DIR = Path(__file__).parent.parent / "secrets"
POLICY_IDS_PATH = SECRETS_DIR / "policy_ids.json"


def is_policy_denied(error: Exception) -> bool:
    """Check if an exception is a policy denial."""
    s = str(error).lower()
    return any(kw in s for kw in ["policy", "denied", "not allowed", "blocked"])


def load_policy_ids() -> dict:
    """Load policy IDs from secrets/policy_ids.json."""
    return json.loads(POLICY_IDS_PATH.read_text())


def verify_policy_rules(client, policy_id: str, expected_rules: int, name: str) -> bool:
    """Fetch a policy and verify it has the expected number of rules."""
    print(f"\n--- Verify {name} policy ({policy_id}) ---")
    policy = client.policies.get(policy_id)
    print(f"  Name: {policy.name}")
    print(f"  Chain: {policy.chain_type}")
    print(f"  Rules: {len(policy.rules)} (expected {expected_rules})")
    for r in policy.rules:
        conds = len(r.conditions)
        print(f"    {r.action:5s} {r.method:30s} '{r.name}' ({conds} conditions)")

    if len(policy.rules) != expected_rules:
        print(f"  FAIL: Expected {expected_rules} rules, got {len(policy.rules)}")
        return False
    print(f"  PASS: Policy verified")
    return True


def test_evm_policy(client, policy_id: str) -> dict:
    """Test EVM policy enforcement with a temporary wallet.

    Returns a dict of test_name → 'PASS' | 'FAIL' | 'ERROR'.
    """
    results = {}

    # Create temp wallet and attach policy
    print("\n--- EVM Policy Enforcement Tests ---")
    wallet = client.wallets.create(chain_type="ethereum")
    wallet_id = wallet.id
    address = wallet.address
    print(f"Created temp EVM wallet: {wallet_id} ({address})")
    client.wallets.update(wallet_id, policy_ids=[policy_id])
    print(f"Attached EVM policy {policy_id}")

    # Test 1: ALLOWED — Sign tx to bridge (value=0, valid calldata)
    print("\n  Test 1: Sign bridge deposit tx (should ALLOW)...")
    try:
        # Encode deposit(uint64) calldata: function selector + amount
        # deposit(uint64): selector = 0xe17376b5 (for the specific bridge)
        # We'll test with a simple tx to the bridge address
        resp = client.wallets.rpc(
            wallet_id,
            method="eth_signTransaction",
            params={
                "transaction": {
                    "to": HL_BRIDGE_CONTRACT,
                    "value": 0,
                    "data": "0xb6b55f250000000000000000000000000000000000000000000000000000000005f5e100",  # deposit(uint256): 100 USDC (100_000_000)
                    "gas_limit": 100000,
                    "nonce": 0,
                    "chain_id": 42161,
                    "max_fee_per_gas": 1000000000,
                    "max_priority_fee_per_gas": 100000000,
                    "type": 2,
                }
            },
        )
        print(f"    PASS: Signed successfully")
        results["evm_allow_bridge_deposit"] = "PASS"
    except Exception as e:
        if is_policy_denied(e):
            print(f"    FAIL: Denied by policy (should have been allowed)")
            results["evm_allow_bridge_deposit"] = "FAIL"
        else:
            print(f"    ERROR: {str(e)[:150]}")
            results["evm_allow_bridge_deposit"] = f"ERROR: {str(e)[:100]}"

    # Test 2: ALLOWED — Sign HL Exchange EIP-712
    print("\n  Test 2: Sign HL Exchange EIP-712 (should ALLOW)...")
    try:
        resp = client.wallets.rpc(
            wallet_id,
            method="eth_signTypedData_v4",
            params={
                "typed_data": {
                    "domain": {
                        "name": "Exchange",
                        "version": "1",
                        "chainId": HL_EXCHANGE_DOMAIN_CHAIN_ID,
                        "verifyingContract": "0x0000000000000000000000000000000000000000",
                    },
                    "types": {
                        "Agent": [
                            {"name": "source", "type": "string"},
                            {"name": "connectionId", "type": "bytes32"},
                        ],
                    },
                    "message": {
                        "source": "a",
                        "connectionId": "0x" + "00" * 32,
                    },
                    "primary_type": "Agent",
                }
            },
        )
        print(f"    PASS: Signed successfully")
        results["evm_allow_hl_exchange"] = "PASS"
    except Exception as e:
        if is_policy_denied(e):
            print(f"    FAIL: Denied by policy (should have been allowed)")
            results["evm_allow_hl_exchange"] = "FAIL"
        else:
            print(f"    ERROR: {str(e)[:150]}")
            results["evm_allow_hl_exchange"] = f"ERROR: {str(e)[:100]}"

    # Test 3: ALLOWED — Sign HL User Action EIP-712
    print("\n  Test 3: Sign HL User Action EIP-712 (should ALLOW)...")
    try:
        resp = client.wallets.rpc(
            wallet_id,
            method="eth_signTypedData_v4",
            params={
                "typed_data": {
                    "domain": {
                        "name": "HyperliquidSignTransaction",
                        "version": "1",
                        "chainId": HL_USER_ACTION_DOMAIN_CHAIN_ID,
                        "verifyingContract": "0x0000000000000000000000000000000000000000",
                    },
                    "types": {
                        "HyperliquidTransaction:Withdraw": [
                            {"name": "hyperliquidChain", "type": "string"},
                            {"name": "destination", "type": "string"},
                            {"name": "amount", "type": "string"},
                            {"name": "time", "type": "uint64"},
                        ],
                    },
                    "message": {
                        "hyperliquidChain": "Mainnet",
                        "destination": address,
                        "amount": "100",
                        "time": 1700000000000,
                    },
                    "primary_type": "HyperliquidTransaction:Withdraw",
                }
            },
        )
        print(f"    PASS: Signed successfully")
        results["evm_allow_hl_user_action"] = "PASS"
    except Exception as e:
        if is_policy_denied(e):
            print(f"    FAIL: Denied by policy (should have been allowed)")
            results["evm_allow_hl_user_action"] = "FAIL"
        else:
            print(f"    ERROR: {str(e)[:150]}")
            results["evm_allow_hl_user_action"] = f"ERROR: {str(e)[:100]}"

    # Test 4: DENIED — Sign tx to random address
    print("\n  Test 4: Sign tx to random address (should DENY)...")
    try:
        resp = client.wallets.rpc(
            wallet_id,
            method="eth_signTransaction",
            params={
                "transaction": {
                    "to": "0x0000000000000000000000000000000000000001",
                    "value": 0,
                    "data": "0x",
                    "gas_limit": 21000,
                    "gas_price": 1000000000,
                    "nonce": 0,
                    "chain_id": 42161,
                }
            },
        )
        print(f"    FAIL: Was allowed (should have been denied)")
        results["evm_deny_random_address"] = "FAIL"
    except Exception as e:
        if is_policy_denied(e):
            print(f"    PASS: Denied by policy as expected")
            results["evm_deny_random_address"] = "PASS"
        else:
            print(f"    ERROR: {str(e)[:150]}")
            results["evm_deny_random_address"] = f"ERROR: {str(e)[:100]}"

    # Test 5: DENIED — Sign tx with value > 0 (ETH drain attempt)
    print("\n  Test 5: Sign tx with value > 0 (should DENY)...")
    try:
        resp = client.wallets.rpc(
            wallet_id,
            method="eth_signTransaction",
            params={
                "transaction": {
                    "to": HL_BRIDGE_CONTRACT,
                    "value": 1000000000000000,  # 0.001 ETH
                    "data": "0x",
                    "gas_limit": 21000,
                    "gas_price": 1000000000,
                    "nonce": 0,
                    "chain_id": 42161,
                }
            },
        )
        print(f"    FAIL: Was allowed (should have been denied)")
        results["evm_deny_eth_value"] = "FAIL"
    except Exception as e:
        if is_policy_denied(e):
            print(f"    PASS: Denied by policy as expected")
            results["evm_deny_eth_value"] = "PASS"
        else:
            print(f"    ERROR: {str(e)[:150]}")
            results["evm_deny_eth_value"] = f"ERROR: {str(e)[:100]}"

    # Test 6: DENIED — Export private key
    print("\n  Test 6: Export private key (should DENY)...")
    try:
        resp = client.wallets.rpc(
            wallet_id,
            method="exportPrivateKey",
            params={},
        )
        print(f"    FAIL: Was allowed (should have been denied)")
        results["evm_deny_export_key"] = "FAIL"
    except Exception as e:
        if is_policy_denied(e):
            print(f"    PASS: Denied by policy as expected")
            results["evm_deny_export_key"] = "PASS"
        else:
            # exportPrivateKey may not be a valid RPC method — check error
            print(f"    INFO: Error (may be method not supported): {str(e)[:150]}")
            results["evm_deny_export_key"] = f"INFO: {str(e)[:100]}"

    # Detach policy
    client.wallets.update(wallet_id, policy_ids=[])
    print(f"\nDetached policy from temp wallet {wallet_id}")

    return results


def test_solana_policy(client, policy_id: str) -> dict:
    """Test Solana policy enforcement with a temporary wallet.

    Note: Solana signing requires a valid serialized transaction, which
    is complex to construct without solana-py. We test what we can
    and document limitations.

    Returns a dict of test_name → 'PASS' | 'FAIL' | 'ERROR' | 'SKIP'.
    """
    results = {}

    print("\n--- Solana Policy Enforcement Tests ---")
    wallet = client.wallets.create(chain_type="solana")
    wallet_id = wallet.id
    address = wallet.address
    print(f"Created temp Solana wallet: {wallet_id} ({address})")
    client.wallets.update(wallet_id, policy_ids=[policy_id])
    print(f"Attached Solana policy {policy_id}")

    # Solana transaction signing requires properly serialized transactions.
    # Testing with a dummy base64 transaction that includes a known program.
    # This is limited — full e2e testing happens in Phase 5.

    # Test 1: Sign a minimal system program transaction
    print("\n  Test 1: Sign system program transfer (should ALLOW)...")
    results["solana_allow_system_transfer"] = "SKIP: requires valid serialized tx"
    print(f"    SKIP: Requires valid serialized Solana transaction (tested in Phase 5)")

    # Test 2: Export private key (should be denied by default-deny)
    print("\n  Test 2: Export private key (should DENY)...")
    try:
        resp = client.wallets.rpc(
            wallet_id,
            method="exportPrivateKey",
            params={},
            chain_type="solana",
        )
        print(f"    FAIL: Was allowed (should have been denied)")
        results["solana_deny_export_key"] = "FAIL"
    except Exception as e:
        if is_policy_denied(e):
            print(f"    PASS: Denied by policy as expected")
            results["solana_deny_export_key"] = "PASS"
        else:
            print(f"    INFO: Error: {str(e)[:150]}")
            results["solana_deny_export_key"] = f"INFO: {str(e)[:100]}"

    # Detach policy
    client.wallets.update(wallet_id, policy_ids=[])
    print(f"\nDetached policy from temp wallet {wallet_id}")

    return results


def main():
    """Run all policy verification tests."""
    policy_ids = load_policy_ids()
    evm_policy_id = policy_ids["evm_policy_id"]
    solana_policy_id = policy_ids.get("solana_policy_id")

    client = _create_privy_client()

    all_results = {}

    # Step 1: Verify policy rules via API
    evm_ok = verify_policy_rules(client, evm_policy_id, 5, "EVM")
    all_results["evm_policy_verified"] = "PASS" if evm_ok else "FAIL"

    if solana_policy_id:
        sol_ok = verify_policy_rules(client, solana_policy_id, 3, "Solana")
        all_results["solana_policy_verified"] = "PASS" if sol_ok else "FAIL"

    # Step 2: Test EVM policy enforcement
    evm_results = test_evm_policy(client, evm_policy_id)
    all_results.update(evm_results)

    # Step 3: Test Solana policy enforcement
    if solana_policy_id:
        sol_results = test_solana_policy(client, solana_policy_id)
        all_results.update(sol_results)

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    passed = 0
    failed = 0
    skipped = 0
    errors = 0
    for test, result in all_results.items():
        status = result.split(":")[0] if ":" in result else result
        icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "⊘", "INFO": "ℹ"}.get(status, "?")
        print(f"  {icon} {test}: {result}")
        if result == "PASS":
            passed += 1
        elif result == "FAIL":
            failed += 1
        elif result.startswith("SKIP"):
            skipped += 1
        else:
            errors += 1

    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped, {errors} errors/info")

    # Save results
    results_path = Path(__file__).parent.parent / "docs" / "policy_verification_results.json"
    results_path.write_text(json.dumps(all_results, indent=2) + "\n")
    print(f"Results saved to {results_path}")

    if failed > 0:
        print("\nWARNING: Some tests FAILED. Review policy rules.")
        sys.exit(1)


if __name__ == "__main__":
    main()
