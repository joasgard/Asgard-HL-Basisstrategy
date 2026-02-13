"""
Test Privy policy rule evaluation order.

Creates a policy with conflicting ALLOW/DENY rules and tests which one wins.
This determines whether Privy uses first-match, deny-overrides, or most-specific.

Results are logged and printed. The test policy is deleted after the test.

Usage:
    .venv/bin/python3 scripts/test_policy_eval_order.py
"""
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.venues.privy_signer import _create_privy_client
from shared.config.wallet_policies import HL_BRIDGE_CONTRACT, USDC_ARBITRUM


def main():
    """Test policy evaluation order by creating conflicting rules."""
    client = _create_privy_client()
    test_policy_id = None
    test_wallet_id = None

    try:
        # ---------------------------------------------------------------
        # Step 1: Create a test policy with ALLOW first, then DENY on
        #         the same method with overlapping conditions.
        #
        # If first-match:  ALLOW wins (first rule matches)
        # If deny-overrides: DENY wins (DENY always takes precedence)
        # If most-specific:  ALLOW wins (more conditions = more specific)
        # ---------------------------------------------------------------
        print("=== Policy Evaluation Order Test ===\n")

        # Test: ALLOW + specific DENY (not catch-all).
        # We already proved: default behavior = deny-if-no-ALLOW-matches.
        # Now test: does a specific DENY override the ALLOW when both match?
        rules = [
            {
                "name": "test_allow_bridge",
                "action": "ALLOW",
                "method": "eth_signTransaction",
                "conditions": [
                    {
                        "field_source": "ethereum_transaction",
                        "field": "to",
                        "operator": "eq",
                        "value": HL_BRIDGE_CONTRACT,
                    },
                ],
            },
            {
                "name": "test_deny_value",
                "action": "DENY",
                "method": "eth_signTransaction",
                "conditions": [
                    {
                        "field_source": "ethereum_transaction",
                        "field": "value",
                        "operator": "gt",
                        "value": "0",
                    },
                ],
            },
        ]

        print("Creating test policy with ALLOW + specific DENY:")
        print(f"  Rule 1 (ALLOW): eth_signTransaction to == {HL_BRIDGE_CONTRACT}")
        print(f"  Rule 2 (DENY):  eth_signTransaction value > 0")
        print()

        test_policy = client.policies.create(
            chain_type="ethereum",
            name="__test_eval_order__",
            rules=rules,
            version="1.0",
        )
        test_policy_id = test_policy.id
        print(f"Created test policy: {test_policy_id}")
        print(f"Rules returned: {len(test_policy.rules)}")
        for r in test_policy.rules:
            print(f"  [{r.id}] {r.action:5s} {r.method} '{r.name}' ({len(r.conditions)} conditions)")
        print()

        # ---------------------------------------------------------------
        # Step 2: Create a temporary test wallet and attach the policy
        # ---------------------------------------------------------------
        print("Creating temporary EVM test wallet...")
        test_wallet = client.wallets.create(chain_type="ethereum")
        test_wallet_id = test_wallet.id
        print(f"Created test wallet: {test_wallet_id} ({test_wallet.address})")

        # Attach the test policy
        client.wallets.update(test_wallet_id, policy_ids=[test_policy_id])
        print(f"Attached policy {test_policy_id} to wallet {test_wallet_id}")
        print()

        # ---------------------------------------------------------------
        # Step 3: Try signing a transaction TO the bridge (should ALLOW
        #         if first-match or most-specific, DENY if deny-overrides)
        # ---------------------------------------------------------------
        print("Test A: Sign tx to bridge contract (matches ALLOW rule)...")
        try:
            response = client.wallets.rpc(
                test_wallet_id,
                method="eth_signTransaction",
                params={
                    "transaction": {
                        "to": HL_BRIDGE_CONTRACT,
                        "value": 0,
                        "data": "0x",
                        "gas_limit": 21000,
                        "gas_price": 1000000000,
                        "nonce": 0,
                        "chain_id": 42161,
                    }
                },
            )
            print(f"  RESULT: ALLOWED (got signed tx)")
            test_a_result = "ALLOWED"
        except Exception as e:
            error_str = str(e)
            if "policy" in error_str.lower() or "denied" in error_str.lower() or "not allowed" in error_str.lower():
                print(f"  RESULT: DENIED by policy")
                test_a_result = "DENIED"
            else:
                print(f"  RESULT: ERROR (not policy-related): {error_str[:200]}")
                test_a_result = f"ERROR: {error_str[:100]}"

        # ---------------------------------------------------------------
        # Step 4: Try signing a transaction to a random address (should
        #         be DENIED by both first-match and deny-overrides)
        # ---------------------------------------------------------------
        print("\nTest B: Sign tx to random address (should always be DENIED)...")
        try:
            response = client.wallets.rpc(
                test_wallet_id,
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
            print(f"  RESULT: ALLOWED (unexpected!)")
            test_b_result = "ALLOWED"
        except Exception as e:
            error_str = str(e)
            if "policy" in error_str.lower() or "denied" in error_str.lower() or "not allowed" in error_str.lower():
                print(f"  RESULT: DENIED by policy (expected)")
                test_b_result = "DENIED"
            else:
                print(f"  RESULT: ERROR: {error_str[:200]}")
                test_b_result = f"ERROR: {error_str[:100]}"

        # ---------------------------------------------------------------
        # Step 4b: Try signing a tx TO the bridge WITH value > 0
        #          (matches both ALLOW and DENY — tests deny-overrides
        #          for SPECIFIC deny rules vs catch-all DENY *)
        # ---------------------------------------------------------------
        print("\nTest C: Sign tx to bridge with value > 0 (matches both ALLOW and DENY)...")
        try:
            response = client.wallets.rpc(
                test_wallet_id,
                method="eth_signTransaction",
                params={
                    "transaction": {
                        "to": HL_BRIDGE_CONTRACT,
                        "value": 1000,
                        "data": "0x",
                        "gas_limit": 21000,
                        "gas_price": 1000000000,
                        "nonce": 0,
                        "chain_id": 42161,
                    }
                },
            )
            print(f"  RESULT: ALLOWED (DENY rule did NOT fire)")
            test_c_result = "ALLOWED"
        except Exception as e:
            error_str = str(e)
            if "policy" in error_str.lower() or "denied" in error_str.lower() or "not allowed" in error_str.lower():
                print(f"  RESULT: DENIED by policy (DENY rule overrides ALLOW)")
                test_c_result = "DENIED"
            else:
                print(f"  RESULT: ERROR: {error_str[:200]}")
                test_c_result = f"ERROR: {error_str[:100]}"

        # ---------------------------------------------------------------
        # Step 5: Analyze results
        # ---------------------------------------------------------------
        print("\n=== Analysis ===")
        print(f"Test A (bridge, value=0):    {test_a_result}")
        print(f"Test B (random, value=0):    {test_b_result}")
        print(f"Test C (bridge, value>0):    {test_c_result}")

        if test_a_result == "ALLOWED" and test_b_result == "DENIED" and test_c_result == "DENIED":
            evaluation_model = "DEFAULT-DENY + SPECIFIC-DENY-OVERRIDES"
            print("\nConclusion: Privy evaluation model:")
            print("  1. Default behavior: DENY if no ALLOW rule matches")
            print("  2. Specific DENY rules override ALLOWs when DENY conditions match")
            print("  3. ALLOW-only policies work (no catch-all DENY needed)")
            print("  4. Specific DENY rules block actions even if an ALLOW also matches")
            print("  => Policy structure: use ALLOWs as allowlist + specific DENYs as guardrails")
        elif test_a_result == "ALLOWED" and test_b_result == "DENIED" and test_c_result == "ALLOWED":
            evaluation_model = "DEFAULT-DENY + ALLOW-FIRST"
            print("\nConclusion: Privy evaluation model:")
            print("  1. Default behavior: DENY if no ALLOW rule matches")
            print("  2. ALLOW rules take precedence over DENY rules (ALLOW-first)")
            print("  3. DENY rules only apply when no ALLOW matches")
            print("  => Policy structure: ALLOW-only. DENY rules are secondary guards.")
        elif test_a_result == "DENIED" and test_b_result == "DENIED" and test_c_result == "DENIED":
            evaluation_model = "DENY-OVERRIDES-ALL"
            print("\nConclusion: Privy uses universal DENY-OVERRIDES.")
            print("  ANY matching DENY blocks regardless of ALLOWs.")
            print("  Cannot have DENY rules alongside ALLOWs for the same method.")
        else:
            evaluation_model = f"UNKNOWN (A={test_a_result}, B={test_b_result}, C={test_c_result})"
            print(f"\nConclusion: Unclear evaluation model.")

        # Save results
        results = {
            "evaluation_model": evaluation_model,
            "test_a_bridge_value0": test_a_result,
            "test_b_random_value0": test_b_result,
            "test_c_bridge_value_gt0": test_c_result,
            "policy_id": test_policy_id,
            "wallet_id": test_wallet_id,
            "rules": [
                {"order": i + 1, "name": r["name"], "action": r["action"], "conditions_count": len(r.get("conditions", []))}
                for i, r in enumerate(rules)
            ],
        }
        results_path = Path(__file__).parent.parent / "docs" / "policy_eval_order_results.json"
        results_path.write_text(json.dumps(results, indent=2))
        print(f"\nResults saved to {results_path}")

    finally:
        # ---------------------------------------------------------------
        # Cleanup: Delete test policy and wallet
        # ---------------------------------------------------------------
        print("\n=== Cleanup ===")
        if test_wallet_id:
            try:
                # Detach policy first
                client.wallets.update(test_wallet_id, policy_ids=[])
                print(f"Detached policy from wallet {test_wallet_id}")
            except Exception as e:
                print(f"Warning: Could not detach policy: {e}")

        if test_policy_id:
            try:
                client.policies.delete(test_policy_id)
                print(f"Deleted test policy {test_policy_id}")
            except Exception as e:
                print(f"Warning: Could not delete test policy: {e}")

        # Note: We don't delete the test wallet because Privy doesn't
        # support wallet deletion. It will be unused.
        if test_wallet_id:
            print(f"Note: Test wallet {test_wallet_id} left intact (Privy doesn't support wallet deletion)")


if __name__ == "__main__":
    main()
