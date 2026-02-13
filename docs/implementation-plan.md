# Server Wallet Implementation Plan

## Stress-Test Revision (Feb 2026)

This plan was stress-tested for production-readiness. Key changes:

**12 new tasks added**:
- N1: Concurrent wallet provisioning guard (advisory lock + UNIQUE constraint) → Phase 2
- N2: Privy signing retry with circuit breaker → Phase 3
- N3: Stuck bridge deposit reconciliation loop → Phase 5
- N4: ETH gas funding strategy for server EVM wallets → Phase 5
- N5: Internal API user_id derivation from JWT (not spoofable header) → Phase 6
- N6: Cooldown bypass prevention (store cooldown-at-close) → Phase 7
- N7: Explicit drawdown formula for deposits/withdrawals → Phase 7
- N8: Policy evaluation order verification → Phase 1
- N9: Withdrawal balance available check (margin in use) → Phase 5
- N10: Position in-memory dict vs DB sync issue → Phase 6
- N11: Per-user concurrency lock via PG advisory lock (not asyncio.Lock) → Phase 7
- N12: Auto-bridge deposit amount capping → Phase 5

**7 steps modified**:
- C1: Auth sync → enqueue provisioning in background (not inline)
- C2: Withdrawal flow → simplify, eliminate condition set dependency
- C3: EVM policy Rule 6 → document ETH funding direction explicitly
- C4: Risk engine proximity key → include chain prefix + persist to DB
- C5: `user_strategy_config` → add `version` column for optimistic locking
- C6: Internal API auth → JWT-based user_id (not X-User-Id header)
- C7: Auto-bridge → cap amount, require manual confirm above threshold

**7 open questions** requiring external verification added.
**8 accepted risks** documented.

---

## Architecture Overview

Every user who signs in gets their own pair of **server wallets** (EVM + Solana) provisioned automatically. All server wallets share the same Privy **policies** (created once at app setup) and the same **key quorum** (our authorization key). The bot signs transactions autonomously using these server wallets.

```
User signs in via Privy
        │
        ▼
Backend checks: does this user have server wallets?
        │
   ┌────┴────┐
   │ No      │ Yes
   ▼         ▼
Create EVM   Load from DB
+ Solana     │
wallets      │
   │         │
   ▼         ▼
Attach shared policies
Store in users table
        │
        ▼
Dashboard shows server wallet addresses
User deposits funds to trade
        │
        ▼
Bot signs autonomously via Privy wallets.rpc()
```

## Current State

- **Key quorum created**: `h50gcppu9f2g2qrk4pgp2eu1` (public key from `secrets/privy_auth.pem`)
- **Test EVM server wallet created**: `c8rps4e97bnbpeqyh880btp2` at `0xB206b9A163C61255Ef8755682C8a3d3C5e9891bE` — signing verified working (to be deleted)
- **Privy SDK**: `privy-client` v0.5.0, authorization key format fix applied in `bot/venues/privy_signer.py`
- **User's embedded wallets** (cannot be signed server-side, will remain for frontend auth only):
  - EVM: `0xd0334405C2858001C6c750CbF34a333639287bc6`
  - Solana: `Anq6fDWf2KvZKsifo6irgbCwt5R3kX1q1tc2GQM1F5n1`

## Contract Addresses (all chains)

### Arbitrum (Chain ID: 42161)
| Contract | Address | Purpose |
|----------|---------|---------|
| USDC (native) | `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` | Stablecoin for trading |
| HL Bridge | `0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7` | Bridge USDC to Hyperliquid |

### Solana
| Contract/Mint | Address | Purpose |
|---------------|---------|---------|
| USDC | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` | Borrow token for Asgard |
| SOL (wrapped) | `So11111111111111111111111111111111111111112` | Collateral |
| jitoSOL | `J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn` | LST collateral |
| jupSOL | `jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v` | LST collateral |
| INF | `5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X6TxNxsi` | LST collateral |
| Marginfi | `MFv2hWf31Z9kbCa1snEPYcvnvbsWBcWAjjaTzMX2Q9` | Lending protocol |
| Kamino | `KLend2g3cP87fffoy8q1mQqGKjrxFtd9BKE1rM5cCp` | Lending protocol |
| Solend | `So1endDqUFYhgUNLA3P8wDxzDEaF1ZpCtiE2YfLJ1` | Lending protocol |
| Drift | `dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH` | Lending protocol |
| Asgard | **PLACEHOLDER** — needs real address | Margin trading |
| System Program | `11111111111111111111111111111111` | SOL transfers |
| Token Program | `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA` | SPL token operations |
| ATA Program | `ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL` | Associated token accounts |
| Compute Budget | `ComputeBudget111111111111111111111111111111` | Transaction compute limits |

### Hyperliquid (EIP-712 domains, not on-chain contracts)
| Domain | chainId | verifyingContract | Purpose |
|--------|---------|-------------------|---------|
| Exchange | 1337 | `0x0000...0000` | Orders, leverage, cancels |
| HyperliquidSignTransaction | 42161 | `0x0000...0000` | Withdrawals, transfers |

---

## Phase 1: Shared Policies (CRITICAL — before any wallets are used)

### What it accomplishes
Create the two reusable Privy policies (EVM + Solana) that will be attached to every user's server wallets. Policies are app-level resources — created once, shared by all wallets.

### Prerequisites
- Key quorum `h50gcppu9f2g2qrk4pgp2eu1` exists (done)
- Authorization key format fix applied (done)
- Contract addresses confirmed (Asgard program ID placeholder noted as gap)

### Steps

#### 1.1 EVM Policy

The EVM wallet does three things:
1. **Approve USDC** on the HL bridge contract
2. **Call bridge deposit()** to send USDC to Hyperliquid
3. **Sign EIP-712 typed data** for Hyperliquid orders/withdrawals

Policy rules:

| # | Rule Name | Method | Action | Conditions |
|---|-----------|--------|--------|------------|
| 1 | Allow USDC approve for bridge | `eth_signTransaction` | ALLOW | `to` == USDC contract AND calldata function == `approve` AND `approve.spender` == HL bridge |
| 2 | Allow bridge deposit | `eth_signTransaction` | ALLOW | `to` == HL bridge AND calldata function == `deposit` |
| 3 | Allow HL Exchange signing | `eth_signTypedData_v4` | ALLOW | domain.name == "Exchange" AND domain.chainId == 1337 |
| 4 | Allow HL User Action signing | `eth_signTypedData_v4` | ALLOW | domain.name == "HyperliquidSignTransaction" AND domain.chainId == 42161 |
| 5 | Restrict chain to Arbitrum | `eth_signTransaction` | DENY | chain_id NOT IN [42161] |
| 6 | Cap ETH value (no native transfers) | `eth_signTransaction` | DENY | value > 0 (prevent ETH drain). Note: ETH gas funding flows INTO the server wallet (signed by the funder's key, not the server wallet). This rule does NOT block incoming ETH. |
| 7 | Block private key export | `exportPrivateKey` | DENY | (unconditional) |
| 8 | Deny all else | `*` | DENY | (unconditional, catch-all) |

**Stateful aggregation** (rolling cap):
- Track cumulative USDC `approve` amounts over 24h rolling window
- Deny if cumulative exceeds configurable cap (default: $50,000)

#### 1.2 Solana Policy

The Solana wallet interacts with Asgard to create/close margin positions.

Policy rules:

| # | Rule Name | Method | Action | Conditions |
|---|-----------|--------|--------|------------|
| 1 | Allow Asgard programs | `signTransaction` | ALLOW | programId IN [Marginfi, Kamino, Solend, Drift, Asgard, System, Token, ATA, ComputeBudget] |
| 2 | Cap SOL transfer | `signTransaction` | ALLOW | System.Transfer.lamports <= configurable cap |
| 3 | Cap SPL token transfer | `signTransaction` | ALLOW | TokenProgram.TransferChecked.amount <= configurable cap |
| 4 | Block private key export | `exportPrivateKey` | DENY | (unconditional) |
| 5 | Deny all else | `*` | DENY | (unconditional) |

**Gap**: No stateful/aggregate policies for Solana (EVM-only). Per-transaction caps are the only limit available.

#### 1.3 Policy configuration

All addresses and limits stored in config (`shared/config/wallet_policies.py`), loaded from env vars:
- `MAX_USDC_PER_TX` — per-transaction USDC cap (default: $10,000)
- `MAX_USDC_DAILY` — 24h rolling cap for EVM (default: $50,000)
- `MAX_SOL_PER_TX` — per-transaction SOL cap in lamports (default: 100 SOL)
- `MAX_SPL_PER_TX` — per-transaction SPL token cap (default: 10,000 USDC worth)
- All contract addresses loaded from settings/env vars

#### 1.4 Verify policy evaluation order (N8)

Before creating policies, verify Privy's rule evaluation semantics:
- **First-match**: Rules evaluated in order, first match wins → catch-all DENY must be last
- **Deny-overrides**: Any DENY blocks regardless of ALLOWs → all ALLOWs must be carved out before the catch-all
- **Most-specific-match**: Most specific rule wins → ordering less critical

Test by creating a policy with conflicting rules and observing behavior. Document the result. If first-match, the tables above must be treated as priority-ordered (top = highest priority).

#### 1.5 Store policy IDs

Save the created policy IDs to config so the provisioning service can attach them to new wallets:
- `EVM_POLICY_ID` — stored in env var or `secrets/policy_ids.json`
- `SOLANA_POLICY_ID` — same

#### 1.6 Policy verification

- After creating each policy, `GET /v1/policies/{id}` to confirm active
- **Test disallowed actions** (using the existing test wallet `c8rps4e97bnbpeqyh880btp2`):
  - Attempt to sign a transaction to a random address → expect DENY
  - Attempt to sign a native ETH transfer with value > 0 → expect DENY
  - Attempt to export private key → expect DENY
- Document results in tracker

### Acceptance criteria
- Both policies created and confirmed via API query
- Policy IDs stored in config
- Disallowed action tests pass (denied as expected)
- All addresses and limits configurable via env vars
- Policy gaps documented

### Risks
- SDK types `chain_type` as `Literal["ethereum"]` — Solana policy creation may need `chain_type="solana"` passed despite type hint
- Privy policy evaluation is best-effort for stateful aggregations (concurrent requests can bypass)
- Asgard program ID is a placeholder — Solana policy can't include it yet
- One policy per wallet limit means all rules must be in a single policy
- `in` operator capped at 100 values (sufficient for our use case)

---

## Phase 2: Wallet Provisioning Service

### What it accomplishes
Build the service that automatically creates and configures server wallets for each user. When a user signs in, the backend checks if they have server wallets; if not, it provisions a pair (EVM + Solana), attaches policies, and stores them in the database.

### Prerequisites
- Phase 1 complete (shared policies exist)

### Steps

#### 2.1 Database migration — add server wallet columns to `users` table

```sql
ALTER TABLE users ADD COLUMN server_evm_wallet_id TEXT;
ALTER TABLE users ADD COLUMN server_evm_address TEXT;
ALTER TABLE users ADD COLUMN server_solana_wallet_id TEXT;
ALTER TABLE users ADD COLUMN server_solana_address TEXT;

-- Prevent duplicate wallet assignment (N1: concurrent provisioning guard)
ALTER TABLE users ADD CONSTRAINT uq_server_evm_wallet UNIQUE (server_evm_wallet_id);
ALTER TABLE users ADD CONSTRAINT uq_server_solana_wallet UNIQUE (server_solana_wallet_id);
```

#### 2.2 Create `bot/venues/server_wallets.py` — provisioning service

```python
class ServerWalletService:
    async def ensure_wallets_for_user(user_id: str, db: Database) -> dict:
        """
        Ensure a user has server wallets. Idempotent.
        Returns {"evm": {"wallet_id", "address"}, "solana": {"wallet_id", "address"}}
        """
        # 1. Check DB for existing wallets
        # 2. If missing, create via Privy API
        # 3. Attach shared policies
        # 4. Store in DB
        # 5. Return wallet info

    async def create_evm_wallet(user_id: str) -> dict:
        """Create EVM server wallet with key quorum + EVM policy."""

    async def create_solana_wallet(user_id: str) -> dict:
        """Create Solana server wallet with key quorum + Solana policy."""

    async def get_user_wallets(user_id: str, db: Database) -> dict:
        """Load user's server wallets from DB."""
```

Key design decisions:
- **Idempotent**: calling `ensure_wallets_for_user` twice is safe
- **Concurrency-safe (N1)**: Uses `SELECT ... FOR UPDATE` or `pg_advisory_lock(hashtext(user_id))` to prevent two concurrent calls from creating duplicate wallets. If the DB write fails after Privy wallet creation, the orphaned Privy wallet is logged for manual cleanup.
- **Atomic**: if EVM creation succeeds but Solana fails, the EVM wallet is still stored (partial state is OK, the next call will create the missing one)
- **Wallet ownership**: each wallet gets `owner_id=None` (server-managed, not user-owned) but is tracked per-user in our DB
- **Key quorum + policies** attached at creation time

#### 2.3 Integrate into auth sync flow (modified per C1)

Update `backend/dashboard/api/auth.py` — `sync_privy_auth()`:
- After verifying the user's Privy token and creating/updating the user record
- **Check if wallets exist** (fast DB query on `server_evm_wallet_id IS NOT NULL`)
- If wallets exist: continue immediately (no latency impact)
- If wallets missing: **enqueue provisioning as background task** (`asyncio.create_task(ensure_wallets_for_user(...))`), return a `"wallets_provisioning": true` flag in the sync response
- Frontend polls `GET /api/v1/wallets/server` (2.4) until wallets are ready
- This avoids adding 1-3s latency to every first login (Privy wallet creation is 2-4 API calls at 200-800ms each)

#### 2.4 Add wallet provisioning endpoint

Create `GET /api/v1/wallets/server` endpoint:
- Returns the current user's server wallet addresses (EVM + Solana)
- If wallets don't exist yet, calls `ensure_wallets_for_user` to create them
- Frontend uses this to show deposit addresses

#### 2.5 Delete test wallet and provision for existing user

- Delete the test wallet `c8rps4e97bnbpeqyh880btp2`
- Run provisioning for the existing user (`did:privy:cmligjikm002b0cielm5urxjj`) to create their production wallets with policies attached

### Acceptance criteria
- New users get server wallets automatically on first sign-in
- Existing users get server wallets on next sign-in (or via API endpoint)
- Wallets have policies attached from creation
- Wallet IDs and addresses stored in `users` table
- Provisioning is idempotent (safe to call multiple times)
- Login doesn't fail if Privy API is temporarily down (graceful degradation)

### Risks
- Privy API rate limits on wallet creation — unlikely issue with low user count
- If wallet creation fails mid-flow (EVM created, Solana not), partial state must be handled
- Wallet creation adds latency to first login (~2-4 API calls)

---

## Phase 3: Signing Layer

### What it accomplishes
Refactor the signing code to use per-user server wallets loaded from the database, with structured logging and policy-aware error handling.

### Prerequisites
- Phase 2 complete (wallets provisioned per user)

### Steps

#### 3.1 Refactor `bot/venues/privy_signer.py`

- Accept `wallet_id` directly (no more address→ID resolution via `wallets.list()`)
- Remove the `_wallet_id_cache` and `_resolve_wallet_id` — wallet IDs come from the DB
- Add structured logging for every signing request
- Add error handling that distinguishes policy rejections (`PermissionDeniedError`) from API errors (`APIConnectionError`)
- Keep the authorization key format fix

#### 3.1a Add signing retry with circuit breaker (N2)

The `PrivyWalletSigner` currently has no retry logic. If the Privy API goes down mid-trade:
- Asgard long is open, but HL short cannot be signed → unhedged exposure
- Attempting to unwind the Asgard position also requires Privy signing → stuck

Add:
- **Bounded retry**: 3 attempts with exponential backoff (1s, 2s, 4s) for transient errors (timeouts, 5xx)
- **Circuit breaker**: After 5 consecutive signing failures across any wallet, pause all signing for 60 seconds. Log at CRITICAL level.
- **Unwind-blocked handling**: If the bot cannot unwind a position because signing is down, flag the position as `STUCK_UNWIND` in DB and alert the operator. Do not silently log and move on — this is a critical state requiring human intervention.

#### 3.2 Create `bot/venues/user_context.py` (or update existing)

A "user context" that carries the user's server wallet IDs through the bot's execution:
```python
@dataclass
class UserTradingContext:
    user_id: str
    evm_wallet_id: str
    evm_address: str
    solana_wallet_id: str
    solana_address: str
```

The bot loads this from the DB at startup (or per-request in dashboard API calls).

#### 3.3 Update `bot/venues/hyperliquid/depositor.py`

- Accept `UserTradingContext` (or wallet_id + address directly)
- Use the user's server EVM wallet for approve + bridge deposit
- Sign via `wallets.rpc()` with the user's EVM `wallet_id`

#### 3.4 Update `bot/venues/hyperliquid/signer.py`

- Accept wallet_id + address from user context
- Use the user's server EVM wallet address as the HL trading address
- Sign via `wallets.rpc()` with the user's EVM `wallet_id`

#### 3.5 Update `bot/venues/asgard/transactions.py`

- Accept wallet_id + address from user context
- Use the user's server Solana wallet for Asgard position transactions
- Sign via `wallets.rpc()` with the user's Solana `wallet_id`

#### 3.6 Update unit tests

- Mock `UserTradingContext` or wallet IDs instead of embedded wallet addresses
- Test policy rejection error handling path

### Acceptance criteria
- All signing uses per-user server wallet IDs from the DB
- Every signature request is logged with: timestamp, user_id, wallet_id, chain, method, action type, result
- Policy rejection errors produce clear log messages distinct from API errors
- All unit tests pass with updated mocks

### Risks
- HL account is tied to the EVM address that deposits — each user's HL account is at their server wallet address
- Existing test mocks need updating

---

## Phase 4: Monitoring & Alerts

### What it accomplishes
Visibility into all wallet operations, balance tracking, and policy violation detection.

### Prerequisites
- Phase 3 complete

### Steps

1. **Structured signing log**: Every `wallets.rpc()` call logs:
   - `user_id`, `wallet_id`, `chain`, `method`, `action_summary`, `result` (success/denied/error), `timestamp`
   - If denied: the error details from Privy API response

2. **Health check endpoint** — add to bot internal API (`/health/wallets`):
   - Per-user: EVM wallet ETH + USDC balance, Solana wallet SOL + USDC balance
   - Per-user: HL clearinghouse deposited balance
   - System-wide: total signing requests (last hour), policy violations (last 24h)

3. **Dashboard integration**:
   - Show the user's server wallet addresses and balances
   - Show deposit instructions specific to their server wallets
   - Show signing activity summary

### Acceptance criteria
- Every signing request produces a structured log entry
- `/health/wallets` endpoint returns per-user balance + activity summary
- Dashboard shows server wallet status for the logged-in user

### Risks
- Minimal — this is observability only

---

## Phase 5: Integration

### What it accomplishes
Wire everything together: deposit/withdrawal flows, bot startup, and end-to-end testing.

### Prerequisites
- Phase 3 + Phase 4 complete
- At least one user has funded server wallets

### Steps

1. **Update deposit flow (modified per C7 — auto-bridge capping)**:
   - Dashboard shows the user's server wallet EVM address as the deposit target
   - User sends USDC from any wallet (embedded, MetaMask, exchange) to their server EVM wallet on Arbitrum
   - Bot detects the deposit via balance polling, then bridges to HL
   - **Amount cap (N12)**: Auto-bridge is capped at the lesser of `user.max_position_pct * total_balance` or a system-wide per-deposit cap (`MAX_AUTO_BRIDGE_USDC`, default $25,000). Deposits above this cap are held in the server wallet and surfaced on the dashboard for manual confirmation.
   - For Solana side: user sends SOL/LSTs to their server Solana wallet address

2. **ETH gas funding strategy (N4)**:
   - Server EVM wallets need ETH on Arbitrum for gas (approve + bridge deposit = ~$0.10-0.50)
   - **Approach**: Admin/operator funds a "gas funder" wallet. A background task checks each active user's server wallet ETH balance. If below `MIN_ETH_FOR_BRIDGE` (0.002 ETH), the gas funder sends a small ETH top-up (0.005 ETH, ~$10 at current prices).
   - EVM policy Rule 6 (deny value > 0) does NOT block incoming ETH — the gas funder signs the transfer with its own key.
   - **Config**: `GAS_FUNDER_PRIVATE_KEY` (stored in secrets), `GAS_TOP_UP_AMOUNT` (default 0.005 ETH), `GAS_CHECK_INTERVAL` (default 1 hour)
   - This is a hard blocker for deposit flow — user cannot bridge USDC without gas.

3. **Update withdrawal flow (simplified per C2)**:
   - User requests withdrawal via dashboard
   - Bot withdraws from HL → user's server EVM wallet on Arbitrum
   - **Available balance check (N9)**: Withdrawal amount is capped at `HL_deposited_balance - margin_in_use_by_open_positions`. If user requests more, return error with available amount. This prevents under-margining open HL positions.
   - User's server wallet now holds USDC on Arbitrum — the user can transfer to any external wallet themselves using any standard wallet interface (MetaMask, etc.)
   - **Eliminated**: The condition set approach for dynamic withdrawal destinations is removed. The server wallet does not need to transfer USDC to the user's embedded wallet — the user controls the server wallet through the dashboard and withdraws externally. This eliminates operational coupling and condition set size limits.

4. **Stuck bridge deposit reconciliation (N3)**:
   - If `HyperliquidDepositor.deposit()` confirms the on-chain bridge tx but HL doesn't credit within 5 minutes, the deposit is in limbo
   - Add a `deposit_stage` column to the deposit tracking: `initiated` → `bridge_confirmed` → `hl_credited`
   - A background reconciliation loop re-polls HL every 60 seconds for deposits stuck at `bridge_confirmed` for > 5 minutes
   - If a deposit remains stuck for > 30 minutes, log at WARNING and surface alert on dashboard
   - HL typically credits within 1-2 minutes; this handles rare bridge congestion

5. **Update bot startup**:
   - Load all active users' wallet contexts from DB
   - Verify wallets exist and have policies (call `wallets.get()`)
   - Verify minimum balance thresholds
   - Log wallet addresses and policy IDs per user

6. **End-to-end test**:
   - User deposits small amount of USDC to server EVM wallet
   - Bot bridges to HL → places trade → closes trade → withdraws back
   - Verify policies block unauthorized actions throughout

### Acceptance criteria
- Full trading flow works with per-user server wallets
- User can deposit to and withdraw from their server wallets via dashboard
- Withdrawal respects available balance (margin in use subtracted)
- Auto-bridge capped; over-threshold deposits require manual confirmation
- Gas funding mechanism works for new server wallets
- Stuck bridge deposits are detected and reconciled
- Bot operates autonomously after deposit
- New users automatically get wallets on sign-in
- Policy enforcement verified in end-to-end test

### Risks
- Each user's HL account is at a different address (their server EVM wallet)
- Privy API availability affects first-login experience
- Gas funder wallet is a centralized component that needs ETH balance monitoring

---

## Phase 6: Multi-Tenant Architecture

### What it accomplishes
Refactor the bot to support N concurrent users. Every visitor signs up via Privy, gets their own server wallets, and the bot trades on their behalf independently. Positions, balances, and errors are fully isolated per user.

### Prerequisites
- Phases 1–5 complete (policies, provisioning, signing, monitoring, deposit/withdrawal flows)

### Existing multi-tenant building blocks (already in codebase)
- **`bot/venues/user_context.py`** — `UserTradingContext` loads per-user wallets from DB, creates user-specific `HyperliquidTrader`, `AsgardPositionManager`, `HyperliquidDepositor`
- **`bot/core/intent_scanner.py`** — fully multi-tenant: queries `position_intents` table, creates `UserTradingContext.from_user_id()` per intent, executes with per-user `PositionManager.from_user_context()`
- **`bot/core/position_monitor.py`** — fully multi-tenant: loads all active positions, groups by `user_id`, creates per-user context, runs risk checks per user
- **`bot/core/position_manager.py`** — has `from_user_context()` class method for per-user instantiation
- **DB `positions` table** — has `user_id` column, persistence layer supports per-user filtering
- **`bot/core/bot.py`** — `_positions` dict is keyed by `user_id → position_id`

### What needs to change

#### 6.1 Replace single bot loop with multi-tenant services

The current `scripts/run_bot.py` creates one `DeltaNeutralBot()` with global wallets and runs a single loop. Replace with:

1. **Global services** (shared across all users):
   - Funding rate monitor (Hyperliquid funding rates are the same for everyone)
   - Market data poller (Asgard rates, SOL price)
   - Opportunity detector (identifies profitable conditions globally)

2. **Per-user services** (instantiated per active user):
   - `IntentScanner` — already multi-tenant, polls `position_intents` table
   - `PositionMonitor` — already multi-tenant, groups positions by user
   - Per-user `PositionManager` created via `UserTradingContext.from_user_context()`

3. **Startup flow**:
   ```
   1. Start global services (funding rates, market data)
   2. Load all active users from DB (users with server wallets + nonzero balance)
   3. Start IntentScanner loop (already iterates over all users' intents)
   4. Start PositionMonitor loop (already iterates over all users' positions)
   5. Start internal API server
   ```

4. **User activation**: A user becomes "active" when they have server wallets and a nonzero deposited balance. Users with zero balance are skipped (not errored).

#### 6.2 Update `UserTradingContext` for server wallets

`UserTradingContext.from_user_id()` currently reads `solana_address` and `evm_address` (embedded wallets) from the `users` table. Update to read the server wallet columns instead:
- `server_evm_wallet_id`, `server_evm_address` (for HL signing)
- `server_solana_wallet_id`, `server_solana_address` (for Asgard signing)
- The Privy `wallet_id` is passed through to the signing layer

**Impact on Phase 3**: The signing layer (`privy_signer.py`) must accept `wallet_id` directly. `UserTradingContext` provides it. This is already planned in Phase 3.1/3.2 but the dependency is explicit here.

#### 6.3 Update internal API for multi-tenant (modified per C6, N5)

Current internal API (`bot/core/internal_api.py`) has no `user_id` filtering:
- `GET /internal/positions` — returns ALL users' positions
- `POST /internal/positions/open` — opens with global wallet
- `POST /internal/positions/{id}/close` — no user validation

Changes:
- All endpoints require `user_id` derived from auth context
- `GET /internal/positions?user_id=X` — returns only that user's positions
- `POST /internal/positions/open` — requires `user_id`, creates per-user `PositionManager`
- `POST /internal/positions/{id}/close` — validates position belongs to requesting user

**Auth model (C6)**: The `X-User-Id` header approach is insufficient — the `server_secret` is a shared secret, and any process that knows it can impersonate any user. Instead:
- Dashboard generates a short-lived JWT (HS256, signed with `server_secret`, 60s TTL) containing `{"user_id": "did:privy:...", "exp": ...}`
- Internal API verifies the JWT signature and extracts `user_id`
- This prevents header spoofing while reusing the existing shared secret as the signing key
- If the dashboard is compromised, the JWT TTL limits the window of impersonation

#### 6.4 Fix risk engine per-user state isolation (modified per C4)

`risk_engine.py` uses `_proximity_start_times` dict keyed by position keys like `"asgard_{pda}"` and `"hyperliquid_{id}"`. These are position-specific but not user-scoped.

Fix:
- Key by `f"{user_id}:asgard_{position_pda}"` and `f"{user_id}:hyperliquid_{position_id}"` to properly namespace
- **Persist proximity tracking to DB or Redis** — in-memory state is lost on restart, meaning a 20-second proximity window could be reset by a bot restart at second 19. Add a `proximity_events` table or use Redis with TTL keys.

#### 6.5 Add per-user pause controller

Current `PauseController` is global — pausing affects all users. Add per-user pause:
- Store pause state per `user_id` in DB (new table or column)
- `check_paused(user_id)` checks both global pause AND user-specific pause
- Dashboard "Pause" button pauses only that user's bot
- Kill switch remains global (emergency stop for all users)

#### 6.6 Per-user error boundaries

Wrap each user's trade execution in isolated error handling:

```python
for user_id in active_users:
    try:
        await process_user(user_id)
    except PolicyDeniedError as e:
        logger.warning(f"Policy rejection for {user_id}: {e}")
        flag_user_for_review(user_id, reason=str(e))
    except Exception as e:
        logger.error(f"Error for {user_id}: {e}", exc_info=True)
        # Continue to next user — NEVER propagate
```

Both `IntentScanner` and `PositionMonitor` already process users independently, but need explicit `try/except` per-user with:
- Policy rejections: flag user, don't retry
- API errors: log, retry on next cycle
- Insufficient balance: skip user, log
- Never propagate one user's error to another

#### 6.7 Resolve position in-memory dict vs DB sync (N10)

`PositionMonitorService._execute_exit()` updates the DB (`is_closed = 1`) and logs the close, but the `DeltaNeutralBot._positions` in-memory dict is never notified. The bot's scan/monitor loops use `self._positions` to count open positions and decide whether to open new ones.

Fix: Use DB as the single source of truth. Remove `DeltaNeutralBot._positions` in-memory cache. Instead:
- `IntentScanner` and `PositionMonitor` already query the DB directly — this is correct
- `bot.py` should query DB for position counts, not maintain a separate dict
- If performance is a concern, add a short-lived cache (30s TTL) that is invalidated on position open/close

#### 6.8 Per-user balance checking in opportunity evaluation

Currently the opportunity detector is global (finds best opportunity for SOL/USDC). For multi-tenant, the bot needs to check each user's balance before executing:
- User A has $10,000 deposited → size accordingly
- User B has $500 deposited → smaller position
- User C has $0 → skip entirely

The opportunity is still detected globally (funding rates are the same), but position sizing is per-user (using `PositionSizer` with that user's balances).

### Acceptance criteria
- Bot supports N concurrent users without code changes
- Each user's positions are isolated (no cross-user data leakage)
- One user's error/failure doesn't affect other users
- Users with zero balance are silently skipped
- Per-user pause/resume works from dashboard
- Global kill switch still stops everything
- Internal API is user-scoped

### Risks
- Privy API rate limits with N users signing concurrently — may need request queuing
- Memory usage scales with number of active users × positions
- Database query load increases linearly with user count
- `IntentScanner` and `PositionMonitor` polling frequency may need tuning for many users

---

## Phase 7: Recursive Intents

### What it accomplishes
Enable the bot to autonomously reopen positions within user-defined parameters. Instead of a one-shot trade, the bot continuously monitors conditions and enters/exits positions based on each user's configured strategy — running indefinitely until manually stopped or until risk limits are hit.

### Prerequisites
- Phase 6 complete (multi-tenant bot loop)

### Existing building blocks
- **`position_intents` table** (migration 007): Has `intent_type`, `user_id`, `asset`, `protocol`, `max_leverage`, `expires_at`, `status`
- **`IntentScanner`**: Already processes intents per-user, creates positions from intent parameters
- **Opportunity detector**: Already evaluates funding rates and carry APY

### Steps

#### 7.1 Intent configuration model

Extend the `position_intents` table (or create a new `user_strategy_config` table) with:

```sql
CREATE TABLE user_strategy_config (
    user_id TEXT PRIMARY KEY REFERENCES users(id),
    enabled BOOLEAN DEFAULT FALSE,
    -- Asset / pair configuration
    assets TEXT[] DEFAULT ARRAY['SOL'],          -- which assets to trade
    protocols TEXT[] DEFAULT NULL,                 -- NULL = any available protocol
    -- Entry thresholds
    min_carry_apy REAL DEFAULT 15.0,              -- minimum net carry APY to enter
    min_funding_rate_8hr REAL DEFAULT 0.005,       -- minimum HL funding rate
    max_funding_volatility REAL DEFAULT 0.5,       -- max funding rate volatility (0-1)
    -- Position sizing
    max_position_pct REAL DEFAULT 0.25,            -- max % of balance per position
    max_concurrent_positions INTEGER DEFAULT 2,    -- max open positions at once
    max_leverage REAL DEFAULT 3.0,                 -- max leverage on Asgard side
    -- Exit thresholds
    min_exit_carry_apy REAL DEFAULT 5.0,           -- close if carry drops below this
    take_profit_pct REAL DEFAULT NULL,             -- close at X% profit (NULL = disabled)
    stop_loss_pct REAL DEFAULT 10.0,               -- close at X% loss
    -- Recurse
    auto_reopen BOOLEAN DEFAULT TRUE,              -- reopen after closing if conditions met
    cooldown_minutes INTEGER DEFAULT 30,            -- wait N minutes after close before reopening
    -- Cooldown enforcement (N6): store the cooldown value at close time
    last_close_time TIMESTAMP DEFAULT NULL,
    cooldown_at_close INTEGER DEFAULT NULL,         -- cooldown_minutes at the time of last close
    -- Optimistic locking (C5)
    version INTEGER DEFAULT 1,
    -- Metadata
    updated_at TIMESTAMP DEFAULT NOW(),
    paused_at TIMESTAMP DEFAULT NULL,
    paused_reason TEXT DEFAULT NULL
);
```

**Sensible defaults**: A user can start with zero configuration — the defaults produce a conservative strategy (15% min carry, 25% max position, 3x leverage, 10% stop loss, auto-reopen enabled).

#### 7.1a Strategy config version column (C5)

Add `version INTEGER DEFAULT 1` to `user_strategy_config` for optimistic locking. The bot reads config + version at scan start. Dashboard updates use `UPDATE ... WHERE user_id = $1 AND version = $2 RETURNING version + 1`. If the config is updated mid-scan, the next scan picks up the new version. This prevents partial reads when a user updates config while a trade decision is in flight.

#### 7.2 Autonomous execution loop

Refactor the scan/execute cycle to be per-user and recursive:

```
Every scan interval (e.g., 60 seconds):
  1. Fetch global market data (funding rates, Asgard rates, prices)
  2. For each active user with strategy enabled:
     a. Load user's strategy config
     b. Check if user is paused → skip
     c. Check if user hit cooldown after last close → skip
     d. Count open positions → skip if at max_concurrent_positions
     e. Check user's balance → skip if zero or below minimum
     f. Evaluate opportunity against user's thresholds:
        - carry_apy >= user.min_carry_apy?
        - funding_rate >= user.min_funding_rate_8hr?
        - funding_volatility <= user.max_funding_volatility?
     g. If opportunity found: size position per user's config, execute entry
     h. Log decision (entered / skipped / why) per user
```

The `PositionMonitor` handles exits (already multi-tenant):
```
Every monitor interval (e.g., 30 seconds):
  For each user's open positions:
    a. Check risk engine (liquidation proximity, margin health)
    b. Check user's exit thresholds (min_exit_carry_apy, take_profit, stop_loss)
    c. If exit triggered: close position, log reason
    d. If auto_reopen enabled: mark user as eligible for re-entry after cooldown
```

#### 7.3 Risk engine integration

Add hard limits that override user parameters. These are system-wide guardrails that no user can exceed:

| Limit | Default | Configurable via | Description |
|-------|---------|------------------|-------------|
| Max drawdown per user | 20% | `RISK_MAX_DRAWDOWN_PCT` | Pause user if account drops 20% from peak |
| Max concurrent positions per user | 3 | `RISK_MAX_POSITIONS` | Hard cap (overrides user config if higher) |
| Max daily trade count per user | 20 | `RISK_MAX_DAILY_TRADES` | Prevent excessive trading |
| Consecutive failure circuit breaker | 3 | `RISK_CIRCUIT_BREAKER_FAILURES` | Pause user after N consecutive failed trades |
| Min position size | $100 | `RISK_MIN_POSITION_USD` | Don't open tiny positions |
| Max position size | $50,000 | `RISK_MAX_POSITION_USD` | Hard cap per position |

**Drawdown tracking (with deposit/withdrawal adjustment per N7)**:
- Track per-user peak balance (high-water mark) in DB
- On each monitor cycle, compare current balance to peak
- If drawdown exceeds threshold: pause user, set `paused_reason = "drawdown_limit"`
- User must manually unpause from dashboard after reviewing
- **Deposit/withdrawal adjustment formula**:
  - On deposit of $X: `new_peak = old_peak + X` (deposit raises the peak 1:1)
  - On withdrawal of $X: `new_peak = old_peak * (balance_after / balance_before)` (proportional reduction)
  - Example: Peak $10k, balance $9k, withdraw $4k → `new_peak = 10k * (5k/9k) = $5,556`
  - This prevents deposits from inflating the drawdown threshold and withdrawals from falsely triggering drawdown limits

**Circuit breaker**:
- Track consecutive failures per user (in memory + DB)
- After N consecutive failed trades (execution errors, not market losses): pause user
- Set `paused_reason = "circuit_breaker: N consecutive failures"`
- Log detailed failure reasons for debugging

**Daily trade count**:
- Track trades per user per day in DB
- If count exceeds limit, skip entry for that user until next day

When the risk engine pauses a user:
1. Set `user_strategy_config.paused_at = NOW()`, `paused_reason = "..."`
2. Log at WARNING level with full context
3. Surface on their dashboard: "Trading paused: [reason]. Review and resume."
4. Do NOT close existing positions (they're monitored separately)

#### 7.4 Manual controls

**Per-user controls** (dashboard):
- **Pause/Resume**: Toggle `user_strategy_config.enabled` or set `paused_at`
- **Emergency close all**: Close all open positions for this user immediately
- **Update strategy**: Modify thresholds via settings page (takes effect on next scan cycle)

**Admin controls**:
- **Global kill switch**: Existing file-based kill switch (`/data/emergency.stop`) — pauses ALL users
- **Admin pause user**: Admin endpoint to pause a specific user
- **Admin dashboard**: View all users' positions, balances, and strategy status (future, not in this phase)

**Dashboard integration**:
- Strategy config page: show current settings, allow editing
- Position status: show open positions, P&L, last trade
- Bot status: "Active" / "Paused (reason)" / "Waiting for deposit"
- History: recent trades with entry/exit reasons

### Acceptance criteria
- Users can configure strategy parameters from the dashboard (or use defaults)
- Bot autonomously opens/closes positions per-user based on their config
- Positions reopen after closing when conditions are met (recursive)
- Risk engine pauses users who hit drawdown, circuit breaker, or daily trade limits
- Paused users see the reason on their dashboard and can resume
- Users can pause/resume and emergency-close from dashboard
- Global kill switch stops all users
- The bot runs indefinitely without manual intervention

### Risks
- **Strategy parameter validation**: Must prevent users from setting dangerous values (e.g., 100x leverage, 0% stop loss). Validate on save with hard min/max bounds.
- **Recursive loops**: If conditions oscillate around thresholds, the bot could rapidly open/close positions. The cooldown timer mitigates this, but monitoring is important.
- **Stale config**: If a user updates their config while a trade is in flight, the new config should only apply to the NEXT trade, not the current one.
- **Peak balance tracking**: The high-water mark must account for deposits/withdrawals, not just trading P&L. A deposit should raise the peak; a withdrawal should lower it proportionally.
- **Concurrent scans (N11)**: If scan interval is shorter than execution time, two scans could try to open positions for the same user simultaneously. Use **PostgreSQL advisory locks** (`SELECT pg_advisory_xact_lock(hashtext(user_id))`) — not `asyncio.Lock` — because advisory locks survive process restarts and work across multiple workers. `asyncio.Lock` is in-memory only and useless in multi-process deployments.

---

## Cross-Phase Dependency Notes

### Gaps in earlier phases revealed by Phase 6/7

**Phase 3 (Signing Layer)**:
- `UserTradingContext.from_user_id()` currently reads `solana_address` and `evm_address` (embedded wallet columns). After Phase 2, it must read `server_evm_wallet_id`, `server_evm_address`, `server_solana_wallet_id`, `server_solana_address` instead. This is a Phase 3 task but the requirement comes from Phase 6.
- The `PrivyWalletSigner` must pass `wallet_id` (not `address`) to `wallets.rpc()`. Phase 3.1 plans this, but Phase 6 makes it mandatory for every user.

**Phase 4 (Monitoring)**:
- Per-user monitoring becomes critical in Phase 6 — the health endpoint must support `?user_id=` filtering and the dashboard must show per-user status.

**Phase 5 (Integration)**:
- Bot startup (5.4) must load ALL active users and start per-user services, not just verify one user's wallets. Phase 6.1 supersedes 5.4.
- ~~The withdrawal condition set (5.3) must be updated whenever a new user signs up.~~ Eliminated by C2 — simplified withdrawal flow.

**Risk engine (`bot/core/risk_engine.py`)**:
- `_proximity_start_times` must be namespaced by user_id — Phase 6.4 (modified per C4). If this isn't done before Phase 7, cross-user state leakage will cause incorrect risk decisions.

**Pause controller (`bot/core/pause_controller.py`)**:
- Must support per-user pause before Phase 7.4 manual controls work. Phase 6.5 adds this.

---

## Open Questions (Requiring External Verification)

| # | Question | Why it Matters | Source to Check |
|---|----------|----------------|-----------------|
| Q1 | How does Privy evaluate policy rules — first-match, deny-overrides, or most-specific? | Determines if our rule ordering is secure. Wrong order could allow unauthorized actions. | Privy docs / support |
| Q2 | What are Privy's rate limits on `wallets.rpc()` calls per app? | Each trade = 2+ signing calls. 50 users × 2 positions × 30s polling = 200 signs/min. Need to know ceiling. | Privy docs / support |
| Q3 | Does depositing via HL bridge to a brand-new address auto-create an HL account? | Each user has a new server wallet address. If HL requires explicit account registration, deposit flow breaks. | HL docs / test |
| Q4 | Can Privy rotate or have multiple active authorization keys simultaneously? | Single auth key = single point of failure. If Privy revokes it, all signing breaks instantly. | Privy docs / support |
| Q5 | Is Asgard position close atomic or multi-step? Is it idempotent? | If close is multi-step and bot crashes between steps, position is in partial-close state. | Asgard docs / test |
| Q6 | What is the max size of a Privy condition set? _(May be moot if C2 withdrawal simplification is adopted)_ | If there is a limit (e.g., 1000 addresses), it caps user count for withdrawal destinations. | Privy docs |
| Q7 | Does Privy policy actually parse EIP-712 domain fields (name, chainId) in `eth_signTypedData_v4` rules? | If not, rules 3/4 provide no security beyond "allow all typed data signing." | Privy docs / test |

---

## Accepted Risks

| # | Risk | Impact | Why Accepted | Mitigation |
|---|------|--------|--------------|------------|
| R1 | Single Privy auth key is SPOF | If compromised, attacker can sign any policy-allowed tx for any user | Key never leaves server; policies limit blast radius; $50k/24h rolling cap | Monitor for anomalous signing volume; key rotation plan (Q4) |
| R2 | 5-minute HL credit polling gap | Deposit returns success before HL credits are confirmed | On-chain bridge tx IS confirmed; HL will credit eventually | N3 reconciliation loop catches stuck deposits |
| R3 | Stateful aggregation (24h cap) is best-effort | Concurrent requests can bypass the rolling cap | Bot is sole signer, controls concurrency; per-tx caps are secondary defense | Rate limiting in signing layer |
| R4 | In-memory pause/circuit-breaker state lost on restart | Circuit breaker fired 10s before restart → not active after restart | Risk conditions re-evaluated immediately on first cycle; Phase 6.5 adds DB-backed pause | C4 adds persistence for proximity tracking |
| R5 | No Solana daily/rolling aggregate caps | Compromised bot could issue unlimited Solana txs within per-tx limits | Asgard positions limited by available collateral; per-tx caps limit individual size | Phase 4 monitoring + alerts detect anomalous volume |
| R6 | Single-leg exposure window (~120s) | Price move during entry/exit → unhedged P&L | Window is short vs typical SOL moves; position sizes are capped | Fill validator catches excessive deviation, triggers emergency close |
| R7 | IntentScanner creates new HyperliquidClient per cycle | Wasteful resource allocation (no connection reuse) | HL API is stateless HTTP; scan interval is 60s; overhead is minimal | Refactored to shared client in Phase 6.1 |
| R8 | No admin dashboard in initial release | Operator has no global view of all users | Per-user dashboard exists; operator uses DB queries for now | Admin dashboard deferred to post-Phase 7 |
