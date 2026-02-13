# Funding Flow Rework: Explicit Hyperliquid Deposit + Withdrawal

## Goal

Change the funding flow so that:
1. User funds Solana wallet (unchanged)
2. User funds Arbitrum wallet with USDC (from any source: CEX, bridge, etc.)
3. User explicitly deposits USDC from Arbitrum into Hyperliquid via our frontend
4. User deploys strategy (bot checks HL balance, not Arbitrum)
5. After position close, funds stay on Hyperliquid
6. User can manually withdraw from HL back to Arbitrum when they choose

## Current Flow (what changes)

```
CURRENT:
  User → funds Arb wallet with USDC
       → opens position
       → bot AUTOMATICALLY bridges Arb → HL during position open
       → position runs
       → position closes
       → funds sit on HL (no withdrawal)
       → user has no way to get funds back from HL

NEW:
  User → funds Arb wallet with USDC
       → clicks "Deposit to Hyperliquid" in our UI (explicit)
       → sees HL balance in dashboard
       → opens position (bot checks HL balance only)
       → position runs
       → position closes
       → funds stay on HL, visible in dashboard
       → user clicks "Withdraw to Arbitrum" when they want funds back
```

---

## Phase 1: Backend — HL Deposit & Withdrawal APIs

### 1.1 New API endpoint: `POST /deposit/bridge-to-hl`

**File:** `backend/dashboard/api/deposit.py` (new)

Purpose: User-initiated bridge from Arbitrum → HL clearinghouse.

```python
# Request
POST /deposit/bridge-to-hl
{
    "amount_usdc": 500.0  # or "all" for full Arbitrum USDC balance
}

# Response (async job)
{
    "job_id": "...",
    "status": "pending"
}
```

Implementation:
- Authenticate user via session
- Load user's EVM address from DB (`users.evm_address`)
- Create an async job (reuse `setup_jobs` table or new `deposit_jobs`)
- Job executes `HyperliquidDepositor.deposit(amount)` in background
- Frontend polls `GET /deposit/jobs/{job_id}` for progress

**Steps inside the job:**
1. Validate amount > 0
2. Check Arbitrum USDC balance >= amount
3. Check Arbitrum ETH balance >= 0.002 (gas for approve + bridge)
4. Call `HyperliquidDepositor.deposit(amount)`
5. Return result with tx hashes

### 1.2 New API endpoint: `POST /withdraw/hl-to-arbitrum`

**File:** `backend/dashboard/api/withdraw.py` (new)

Purpose: User-initiated withdrawal from HL clearinghouse → Arbitrum wallet.

```python
# Request
POST /withdraw/hl-to-arbitrum
{
    "amount_usdc": 500.0
}

# Response (async job)
{
    "job_id": "...",
    "status": "pending"
}
```

Implementation:
- Authenticate user via session
- Load user's EVM address from DB
- Validate: user has no open positions (safety check — HL margin would be locked)
- Create async job
- Job calls HL exchange API `withdraw3` action via `HyperliquidSigner`
- Poll for Arbitrum USDC balance increase

### 1.3 New: `HyperliquidDepositor.withdraw()` method

**File:** `bot/venues/hyperliquid/depositor.py`

Add a `withdraw` method alongside the existing `deposit`:

```python
@dataclass
class WithdrawResult:
    success: bool
    amount_usdc: Optional[Decimal] = None
    error: Optional[str] = None

async def withdraw(self, amount_usdc: float) -> WithdrawResult:
    """
    Withdraw USDC from HL clearinghouse to Arbitrum wallet.

    Uses HL's withdraw3 API action (user-signed via EIP-712).
    HL processes withdrawals in batches; funds typically arrive
    on Arbitrum within a few minutes.
    """
```

The withdraw3 action is already supported by `HyperliquidSigner.sign_user_signed_action()` — just needs to be wired up:
- Build `{"type": "withdraw3", "hyperliquidChain": "Arbitrum", "signatureChainId": "0xa4b1", "amount": str(raw_amount), "time": nonce, "destination": wallet_address}`
- Sign with `signer.sign_user_signed_action(action, nonce)`
- POST to `https://api.hyperliquid.xyz/exchange`

### 1.4 Update: `GET /balances` response

**File:** `backend/dashboard/api/balances.py`

Ensure the balances endpoint returns HL clearinghouse balance prominently:

```python
# Current response already includes hl_balance, but verify it's:
{
    "solana": {"sol": 1.5, "usdc": 5000.0},
    "arbitrum": {"eth": 0.01, "usdc": 200.0},
    "hyperliquid": {"usdc": 3000.0, "withdrawable": 3000.0},
    "has_sufficient_funds": true
}
```

### 1.5 Update: `GET /balances/check` (trading readiness)

**File:** `backend/dashboard/api/balances.py`

Change the `can_trade` check:

```python
# BEFORE: checked Arbitrum USDC
can_trade = (
    sol_balance >= 0.05 and
    solana_usdc >= 10 and
    arb_usdc >= 10  # <-- this checked Arbitrum
)

# AFTER: check HL clearinghouse instead
can_trade = (
    sol_balance >= 0.05 and
    solana_usdc >= 10 and
    hl_usdc >= 10  # <-- check Hyperliquid
)
```

### 1.6 Register new routes

**File:** `backend/dashboard/main.py`

- Import and register the new `/deposit` and `/withdraw` routers
- Both require authenticated session

---

## Phase 2: Bot — Remove Auto-Bridge from Position Open

### 2.1 Remove auto-bridge from `PositionManager._check_wallet_balance()`

**File:** `bot/core/position_manager.py`

Current logic (REMOVE):
```python
if hl_balance < margin_needed:
    shortfall = margin_needed - hl_balance
    arb_usdc = await arbitrum_client.get_usdc_balance()
    if arb_usdc >= shortfall:
        self._needs_bridge_deposit = True  # REMOVE
        self._bridge_deposit_amount = shortfall  # REMOVE
    else:
        return False
```

New logic (REPLACE WITH):
```python
if hl_balance < margin_needed:
    logger.warning(
        f"Insufficient HL balance: {hl_balance} < {margin_needed}. "
        f"User must deposit more USDC to Hyperliquid."
    )
    return False  # Fail preflight — user must deposit via frontend
```

### 2.2 Remove bridge step from `PositionManager.open_position()`

**File:** `bot/core/position_manager.py`

Remove the conditional bridge between Asgard open and HL short open:
```python
# REMOVE this block:
if self._needs_bridge_deposit and self._depositor:
    await self._depositor.deposit(self._bridge_deposit_amount)
```

The `open_position` flow becomes:
1. Run preflight checks (HL balance must already be sufficient)
2. Open Asgard long
3. Open Hyperliquid short (no bridge step in between)

### 2.3 Remove `_needs_bridge_deposit` state

**File:** `bot/core/position_manager.py`

Remove these instance variables:
- `self._needs_bridge_deposit`
- `self._bridge_deposit_amount`

### 2.4 Remove Arbitrum ETH check from preflight

**File:** `bot/core/position_manager.py`

Since we no longer bridge during position open, the preflight doesn't need to verify Arbitrum ETH for gas. Remove:
```python
# REMOVE: arb_eth_balance check for bridge gas
# ETH is only needed when user explicitly deposits via frontend
```

Preflight now checks only:
- **Solana:** SOL for gas + USDC for Asgard collateral
- **Hyperliquid:** USDC clearinghouse balance for short margin

### 2.5 Verify no auto-withdrawal after position close

**Files:** `bot/core/bot.py`, `bot/core/position_monitor.py`

Verify (no changes expected — just confirm):
- `_execute_exit()` in bot.py closes HL short + Asgard long, does NOT withdraw from HL
- `_execute_exit()` in position_monitor.py closes HL short + Asgard long, does NOT withdraw from HL
- Funds remain in HL clearinghouse after close ✓

### 2.6 Update `PositionManagerResult` error messages

**File:** `bot/core/position_manager.py`

When HL balance is insufficient, return a clear error:
```python
PositionManagerResult(
    success=False,
    error="Insufficient Hyperliquid balance. Please deposit USDC to Hyperliquid from the dashboard.",
    stage="preflight_hl_balance",
)
```

---

## Phase 3: Frontend — Deposit Flow

### 3.1 Rework `DepositModal.tsx`

**File:** `frontend/src/components/modals/DepositModal.tsx`

Transform from a simple address display into a 3-step guided flow:

**Step 1: Fund Solana** (for Asgard long leg)
- Show Solana wallet address + QR code
- Show current SOL + USDC balances
- Checkmark when: SOL >= 0.1 AND USDC >= minimum for position
- Label: "Step 1: Send SOL and USDC to your Solana wallet"

**Step 2: Fund Arbitrum** (intermediate step)
- Show Arbitrum wallet address + QR code
- Show current ETH + USDC balances
- Checkmark when: USDC > 0 AND ETH >= 0.002
- Label: "Step 2: Send USDC to your Arbitrum wallet"
- Note: "You can send from any exchange or wallet. Make sure to use the Arbitrum network."

**Step 3: Deposit to Hyperliquid** (new — the key change)
- Show current Arbitrum USDC balance
- Show current HL clearinghouse balance
- Amount input (default: full Arbitrum USDC balance)
- "Deposit to Hyperliquid" button
- Progress indicator:
  - "Approving USDC..." (if needed)
  - "Bridging to Hyperliquid..."
  - "Waiting for confirmation..." (polling)
  - "Deposit complete!" ✓
- Checkmark when: HL balance >= minimum for position
- Label: "Step 3: Move USDC into Hyperliquid"

**State management:**
- Track which step is active/complete based on balances
- Auto-advance: when Step 2 balance detected, highlight Step 3
- Allow re-deposit: user can deposit more anytime

### 3.2 New API client functions

**File:** `frontend/src/api/deposit.ts` (new)

```typescript
export const depositApi = {
    bridgeToHL: (amount: number) =>
        apiClient.post('/deposit/bridge-to-hl', { amount_usdc: amount }),

    getJobStatus: (jobId: string) =>
        apiClient.get(`/deposit/jobs/${jobId}`),

    withdrawToArbitrum: (amount: number) =>
        apiClient.post('/withdraw/hl-to-arbitrum', { amount_usdc: amount }),

    getWithdrawJobStatus: (jobId: string) =>
        apiClient.get(`/withdraw/jobs/${jobId}`),
};
```

### 3.3 New `WithdrawModal.tsx`

**File:** `frontend/src/components/modals/WithdrawModal.tsx` (new)

Simple modal for withdrawing HL funds back to Arbitrum:

- Show HL clearinghouse balance (total and withdrawable)
- Show Arbitrum USDC balance
- Amount input with "Max" button
- Safety check: warn if user has open positions ("Withdrawing may affect margin")
- Block withdrawal if user has open positions
- "Withdraw to Arbitrum" button
- Progress indicator:
  - "Submitting withdrawal..."
  - "Processing..." (HL batches withdrawals)
  - "Withdrawal complete!" ✓
- Show updated Arbitrum balance after completion

### 3.4 Update `OpenPositionButton.tsx`

**File:** `frontend/src/components/dashboard/OpenPositionButton.tsx`

Change the funding check:
```typescript
// BEFORE: checked arb_usdc
const canTrade = balances?.has_sufficient_funds;

// The backend /balances/check already updated (Phase 1.5)
// to check HL balance instead of Arbitrum — no frontend change needed
// for the check itself.

// BUT: update the "Deposit Required" message:
// BEFORE: "Send USDC to Arbitrum"
// AFTER: "Deposit USDC to Hyperliquid"
```

When "Deposit Required" is clicked, open DepositModal at Step 3 if Arbitrum already has USDC.

### 3.5 Update `Layout.tsx`

**File:** `frontend/src/components/layout/Layout.tsx`

Add "Withdraw" button next to "Deposit" in header (only show when HL balance > 0):
```tsx
{hlBalance > 0 && (
    <button onClick={() => openModal('withdraw')}>Withdraw</button>
)}
```

Register `WithdrawModal` alongside `DepositModal`.

### 3.6 Update `uiStore.ts`

**File:** `frontend/src/stores/uiStore.ts`

The 'withdraw' modal type already exists in the union type. No changes needed.

### 3.7 Update `useBalances` hook

**File:** `frontend/src/hooks/useBalances.ts`

Ensure `hlBalance` (HL clearinghouse USDC) is exposed as a first-class value. It may already be — verify and adjust if needed.

### 3.8 Update `QuickStats.tsx`

**File:** `frontend/src/components/dashboard/QuickStats.tsx`

Show HL balance prominently as the primary "Trading Balance":
```
Trading Balance: $3,000.00 USDC (on Hyperliquid)
Solana Wallet:   $5,000.00 USDC + 1.5 SOL
Arbitrum Wallet: $200.00 USDC  [← only shown if > 0]
```

---

## Phase 4: Setup / Onboarding Validators

### 4.1 Update funding validation

**File:** `backend/dashboard/setup/validators.py`

Change minimum requirements:
```python
# BEFORE
MIN_EVM_USDC = Decimal("100")  # Arbitrum USDC

# AFTER
MIN_HL_USDC = Decimal("100")   # Hyperliquid clearinghouse USDC
# Keep MIN_EVM_USDC but reduce or remove — Arbitrum is just a pass-through now
```

Update `validate_wallet_funding()`:
```python
# Add HL balance check
hl_balance = await hl_trader.get_deposited_balance()
hl_funded = hl_balance >= MIN_HL_USDC

# FundingStatus gets a new field
@dataclass
class FundingStatus:
    evm_funded: bool               # Has USDC on Arbitrum (informational only)
    solana_sol_funded: bool        # Has >= 0.1 SOL
    solana_usdc_funded: bool       # Has >= 100 USDC
    hl_funded: bool                # Has >= 100 USDC on HL (NEW - required)
    balances: Dict[str, Decimal]
```

### 4.2 Update setup steps

**File:** `backend/dashboard/setup/steps.py`

Update `check_funding()` to include HL balance in the response:
```python
async def check_funding(self) -> Dict:
    # ... existing Solana + Arbitrum checks ...
    # ADD:
    hl_balance = await self._get_hl_balance(user_id)
    return {
        "solana": {"sol": sol_balance, "usdc": sol_usdc},
        "arbitrum": {"eth": eth_balance, "usdc": arb_usdc},
        "hyperliquid": {"usdc": hl_balance},  # NEW
        "ready": sol_funded and hl_funded,  # Changed: HL instead of Arb
    }
```

---

## Phase 5: Tests

### 5.1 Backend API tests

**New file:** `tests/unit/dashboard/test_deposit_api.py`
- Test `POST /deposit/bridge-to-hl` with valid/invalid amounts
- Test job creation and status polling
- Test insufficient balance handling
- Test unauthenticated access blocked

**New file:** `tests/unit/dashboard/test_withdraw_api.py`
- Test `POST /withdraw/hl-to-arbitrum` with valid/invalid amounts
- Test blocked when open positions exist
- Test job creation and status polling

### 5.2 Bot tests

**Update:** `tests/unit/core/test_position_manager.py`
- Remove tests for `_needs_bridge_deposit` / `_bridge_deposit_amount`
- Add test: preflight fails with clear message when HL balance insufficient
- Add test: preflight passes when HL balance sufficient (no Arbitrum check)
- Add test: open_position has no bridge step

**New file:** `tests/unit/venues/test_hyperliquid_depositor.py` (expand)
- Test `withdraw()` method
- Test `withdraw()` with insufficient balance
- Test `withdraw()` blocked when positions open

### 5.3 Frontend tests

**Update:** `frontend/src/components/modals/__tests__/` (if exists)
- Test DepositModal 3-step flow
- Test bridge button triggers API call
- Test progress indicator states

**New:** Test WithdrawModal
- Test amount input validation
- Test open position warning
- Test withdrawal flow

### 5.4 Integration tests

**Update:** `tests/integration/test_full_entry_flow.py`
- Remove any bridge-during-open assertions
- Add test: entry fails gracefully when HL balance insufficient

---

## Phase 6: Migration (if needed)

### 6.1 Optional: Deposit/withdrawal history table

**File:** `migrations/010_deposit_history.sql`

```sql
CREATE TABLE IF NOT EXISTS deposit_history (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    direction TEXT NOT NULL,  -- 'deposit' or 'withdraw'
    amount_usdc REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/completed/failed
    approve_tx_hash TEXT,
    bridge_tx_hash TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_deposit_history_user ON deposit_history(user_id, created_at DESC);
```

This is optional but useful for:
- Showing deposit/withdrawal history in the frontend
- Debugging bridge issues
- Audit trail

---

## File Change Summary

### New files (6)
| File | Purpose |
|------|---------|
| `backend/dashboard/api/deposit.py` | Deposit + bridge API endpoints |
| `backend/dashboard/api/withdraw.py` | Withdrawal API endpoints |
| `frontend/src/api/deposit.ts` | Frontend API client for deposit/withdraw |
| `frontend/src/components/modals/WithdrawModal.tsx` | Withdrawal modal component |
| `tests/unit/dashboard/test_deposit_api.py` | Deposit API tests |
| `tests/unit/dashboard/test_withdraw_api.py` | Withdrawal API tests |

### Modified files (14)
| File | Change |
|------|--------|
| `bot/core/position_manager.py` | Remove auto-bridge logic, HL-only preflight |
| `bot/venues/hyperliquid/depositor.py` | Add `withdraw()` method + `WithdrawResult` |
| `backend/dashboard/main.py` | Register deposit/withdraw routers |
| `backend/dashboard/api/balances.py` | Update `can_trade` check to use HL balance |
| `backend/dashboard/setup/validators.py` | Add `hl_funded` to FundingStatus, update minimums |
| `backend/dashboard/setup/steps.py` | Include HL balance in funding check |
| `frontend/src/components/modals/DepositModal.tsx` | Rework into 3-step guided flow |
| `frontend/src/components/dashboard/OpenPositionButton.tsx` | Update "deposit required" message |
| `frontend/src/components/dashboard/QuickStats.tsx` | Show HL balance as primary trading balance |
| `frontend/src/components/layout/Layout.tsx` | Add Withdraw button, register WithdrawModal |
| `frontend/src/hooks/useBalances.ts` | Ensure HL balance is first-class |
| `tests/unit/core/test_position_manager.py` | Remove bridge tests, add HL-only preflight tests |
| `tests/integration/test_full_entry_flow.py` | Remove bridge-during-open assertions |
| `migrations/010_deposit_history.sql` | Optional: deposit/withdrawal tracking table |

### Files verified (no changes needed)
| File | Why |
|------|-----|
| `bot/core/bot.py` | `_execute_exit` already does not withdraw from HL ✓ |
| `bot/core/position_monitor.py` | `_execute_exit` already does not withdraw from HL ✓ |
| `bot/venues/hyperliquid/signer.py` | Already supports `sign_user_signed_action` for withdraw ✓ |
| `bot/venues/hyperliquid/trader.py` | Already has `get_deposited_balance()` ✓ |
| `frontend/src/stores/uiStore.ts` | Already has 'withdraw' modal type ✓ |

---

## Implementation Order

Recommended sequence (each phase is independently testable):

1. **Phase 2** (Bot) — Remove auto-bridge. Safest to do first since it's subtractive.
2. **Phase 1** (Backend APIs) — Add deposit/withdraw endpoints.
3. **Phase 4** (Validators) — Update funding checks.
4. **Phase 3** (Frontend) — Rework UI to use new APIs.
5. **Phase 5** (Tests) — Update and add tests throughout.
6. **Phase 6** (Migration) — Add deposit history table if desired.

---

## Risk Considerations

1. **Users with funds on Arbitrum but not HL:** After this change, existing users who have USDC on Arbitrum but haven't deposited to HL will see "Deposit Required". The deposit modal should detect this and guide them to Step 3 (bridge to HL).

2. **Position close during bridge:** If a user initiates a bridge while a position is closing, the HL balance check in the withdrawal API prevents withdrawing locked margin.

3. **Bridge failures:** The existing `HyperliquidDepositor` already handles approve/bridge failures gracefully with `DepositResult.error`. The frontend job polling shows the error to the user.

4. **HL withdrawal timing:** Hyperliquid processes withdrawals in batches (typically ~1 minute). The withdrawal job should poll for Arbitrum balance increase with a reasonable timeout (5 minutes).
