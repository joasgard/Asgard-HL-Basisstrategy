"""
Wallet policy configuration for Privy server wallets.

Defines contract addresses, program IDs, and policy limits used to construct
Privy policies for EVM and Solana server wallets. All values are configurable
via environment variables with sensible defaults.

See docs/implementation-plan.md Phase 1 for policy rule tables.
"""
import os
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Contract / Program Addresses
# ---------------------------------------------------------------------------

# Arbitrum (Chain ID 42161)
ARBITRUM_CHAIN_ID = 42161

USDC_ARBITRUM = os.getenv(
    "USDC_ARBITRUM_ADDRESS",
    "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
)

HL_BRIDGE_CONTRACT = os.getenv(
    "HL_BRIDGE_CONTRACT",
    "0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7",
)

# Hyperliquid EIP-712 domains
HL_EXCHANGE_DOMAIN_NAME = "Exchange"
HL_EXCHANGE_DOMAIN_CHAIN_ID = 1337

HL_USER_ACTION_DOMAIN_NAME = "HyperliquidSignTransaction"
HL_USER_ACTION_DOMAIN_CHAIN_ID = ARBITRUM_CHAIN_ID

# Solana program IDs
SOLANA_PROGRAMS = {
    "system": "11111111111111111111111111111111",
    "token": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "ata": "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    "compute_budget": "ComputeBudget111111111111111111111111111111",
    "marginfi": "MFv2hWf31Z9kbCa1snEPYcvnvbsWBcWAjjaTzMX2Q9",
    "kamino": "KLend2g3cP87fffoy8q1mQqGKjrxFtd9BKE1rM5cCp",
    "solend": "So1endDqUFYhgUNLA3P8wDxzDEaF1ZpCtiE2YfLJ1",
    "drift": "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH",
}

# Asgard program ID — placeholder until resolved (see G1 in tracker)
ASGARD_PROGRAM_ID = os.getenv("ASGARD_PROGRAM_ID", "")

USDC_SOLANA_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# ---------------------------------------------------------------------------
# Policy Limits
# ---------------------------------------------------------------------------

# EVM: Per-transaction USDC cap (in token units, USDC has 6 decimals)
MAX_USDC_PER_TX = int(os.getenv("MAX_USDC_PER_TX", "10000")) * 10**6  # $10,000

# EVM: 24-hour rolling USDC approve cap (for stateful aggregation)
MAX_USDC_DAILY = int(os.getenv("MAX_USDC_DAILY", "50000")) * 10**6  # $50,000

# Solana: Per-transaction SOL cap in lamports (1 SOL = 1e9 lamports)
MAX_SOL_PER_TX = int(os.getenv("MAX_SOL_PER_TX", "100")) * 10**9  # 100 SOL

# Solana: Per-transaction SPL token cap (in token units, USDC = 6 decimals)
MAX_SPL_PER_TX = int(os.getenv("MAX_SPL_PER_TX", "10000")) * 10**6  # $10,000

# ---------------------------------------------------------------------------
# Key Quorum
# ---------------------------------------------------------------------------

KEY_QUORUM_ID = os.getenv(
    "PRIVY_KEY_QUORUM_ID",
    "h50gcppu9f2g2qrk4pgp2eu1",
)

# ---------------------------------------------------------------------------
# ERC-20 ABI fragments (for calldata conditions)
# ---------------------------------------------------------------------------

ERC20_APPROVE_ABI = [
    {
        "name": "approve",
        "type": "function",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

# ERC-20 transfer ABI fragment (for USDC transfer to bridge)
ERC20_TRANSFER_ABI = [
    {
        "name": "transfer",
        "type": "function",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]


# ---------------------------------------------------------------------------
# Policy Rule Builders
# ---------------------------------------------------------------------------

def get_allowed_solana_program_ids() -> List[str]:
    """Return the list of program IDs allowed by the Solana policy.

    Includes all known lending protocols, system programs, and Asgard
    if its program ID has been configured.
    """
    program_ids = list(SOLANA_PROGRAMS.values())
    if ASGARD_PROGRAM_ID:
        program_ids.append(ASGARD_PROGRAM_ID)
    return program_ids


@dataclass(frozen=True)
class EVMPolicyConfig:
    """Configuration values for building the EVM policy rules."""
    usdc_contract: str = USDC_ARBITRUM
    bridge_contract: str = HL_BRIDGE_CONTRACT
    allowed_chain_id: int = ARBITRUM_CHAIN_ID
    max_usdc_per_tx: int = MAX_USDC_PER_TX
    max_usdc_daily: int = MAX_USDC_DAILY
    hl_exchange_domain_name: str = HL_EXCHANGE_DOMAIN_NAME
    hl_exchange_domain_chain_id: int = HL_EXCHANGE_DOMAIN_CHAIN_ID
    hl_user_action_domain_name: str = HL_USER_ACTION_DOMAIN_NAME
    hl_user_action_domain_chain_id: int = HL_USER_ACTION_DOMAIN_CHAIN_ID


@dataclass(frozen=True)
class SolanaPolicyConfig:
    """Configuration values for building the Solana policy rules."""
    allowed_program_ids: List[str] = field(
        default_factory=get_allowed_solana_program_ids
    )
    max_sol_per_tx: int = MAX_SOL_PER_TX
    max_spl_per_tx: int = MAX_SPL_PER_TX
    usdc_mint: str = USDC_SOLANA_MINT


def build_evm_policy_rules(config: EVMPolicyConfig = EVMPolicyConfig()) -> list:
    """Build EVM policy rules for Privy server wallets.

    Privy's evaluation model (verified in task 1.4a):
      - Default: DENY if no ALLOW rule matches (implicit deny-all)
      - Specific DENY rules override ALLOWs when DENY conditions match
      - Catch-all ``DENY *`` MUST NOT be used (it overrides ALL ALLOWs)

    Structure: ALLOW rules form the allowlist; specific DENY rules act as
    guardrails within the allowed scope.

    Returns a list of rule dicts matching Privy PolicyCreateParams.Rule format.
    """
    return [
        # Rule 1: Allow USDC approve for HL bridge
        {
            "name": "allow_usdc_approve_for_bridge",
            "action": "ALLOW",
            "method": "eth_signTransaction",
            "conditions": [
                {
                    "field_source": "ethereum_transaction",
                    "field": "to",
                    "operator": "eq",
                    "value": config.usdc_contract,
                },
                {
                    "field_source": "ethereum_calldata",
                    "abi": ERC20_APPROVE_ABI,
                    "field": "approve.spender",
                    "operator": "eq",
                    "value": config.bridge_contract,
                },
            ],
        },
        # Rule 2: Allow USDC transfer to HL bridge (with per-tx cap)
        {
            "name": "allow_usdc_transfer_to_bridge",
            "action": "ALLOW",
            "method": "eth_signTransaction",
            "conditions": [
                {
                    "field_source": "ethereum_transaction",
                    "field": "to",
                    "operator": "eq",
                    "value": config.usdc_contract,
                },
                {
                    "field_source": "ethereum_calldata",
                    "abi": ERC20_TRANSFER_ABI,
                    "field": "transfer.to",
                    "operator": "eq",
                    "value": config.bridge_contract,
                },
                {
                    "field_source": "ethereum_calldata",
                    "abi": ERC20_TRANSFER_ABI,
                    "field": "transfer.amount",
                    "operator": "lte",
                    "value": str(config.max_usdc_per_tx),
                },
            ],
        },
        # Rule 3: Allow HL Exchange EIP-712 signing (orders, leverage, cancels)
        {
            "name": "allow_hl_exchange_signing",
            "action": "ALLOW",
            "method": "eth_signTypedData_v4",
            "conditions": [
                {
                    "field_source": "ethereum_typed_data_domain",
                    "field": "chainId",
                    "operator": "eq",
                    "value": str(config.hl_exchange_domain_chain_id),
                },
            ],
        },
        # Rule 4: Allow HL User Action signing (withdrawals, transfers)
        {
            "name": "allow_hl_user_action_signing",
            "action": "ALLOW",
            "method": "eth_signTypedData_v4",
            "conditions": [
                {
                    "field_source": "ethereum_typed_data_domain",
                    "field": "chainId",
                    "operator": "eq",
                    "value": str(config.hl_user_action_domain_chain_id),
                },
            ],
        },
        # Rule 5: Deny native ETH value transfers (prevent ETH drain).
        # This is a guardrail — overrides ALLOWs when value > 0.
        # ETH gas funding flows INTO the server wallet (signed by the
        # funder's key, not this wallet), so this rule cannot block it.
        {
            "name": "deny_native_eth_transfers",
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
        # NOTE: No catch-all DENY or DENY exportPrivateKey needed.
        # Privy's default behavior denies any request that doesn't match
        # an ALLOW rule. Catch-all DENY * would override all ALLOWs.
        # exportPrivateKey is implicitly denied (no ALLOW for it).
        #
        # Chain restriction (plan Rule 5) is also omitted — Privy tx
        # conditions don't support chain_id field. Chain is enforced by
        # wallet creation chain + caip2 param at RPC call time.
    ]


def build_solana_policy_rules(
    config: SolanaPolicyConfig = SolanaPolicyConfig(),
) -> list:
    """Build Solana policy rules for Privy server wallets.

    Same evaluation model as EVM: default-deny + specific DENY overrides.
    No catch-all DENY needed.

    Returns a list of rule dicts matching Privy PolicyCreateParams.Rule format.
    """
    return [
        # Rule 1: Allow known Asgard / lending / system programs
        {
            "name": "allow_known_programs",
            "action": "ALLOW",
            "method": "signTransaction",
            "conditions": [
                {
                    "field_source": "solana_program_instruction",
                    "field": "programId",
                    "operator": "in",
                    "value": config.allowed_program_ids,
                },
            ],
        },
        # Rule 2: Cap SOL transfer per-transaction
        {
            "name": "cap_sol_transfer",
            "action": "ALLOW",
            "method": "signTransaction",
            "conditions": [
                {
                    "field_source": "solana_system_program_instruction",
                    "field": "Transfer.lamports",
                    "operator": "lte",
                    "value": str(config.max_sol_per_tx),
                },
            ],
        },
        # Rule 3: Cap SPL token transfer per-transaction
        {
            "name": "cap_spl_token_transfer",
            "action": "ALLOW",
            "method": "signTransaction",
            "conditions": [
                {
                    "field_source": "solana_token_program_instruction",
                    "field": "TransferChecked.amount",
                    "operator": "lte",
                    "value": str(config.max_spl_per_tx),
                },
            ],
        },
        # NOTE: No catch-all DENY needed — Privy default-denies
        # unmatched requests. exportPrivateKey implicitly denied.
    ]
