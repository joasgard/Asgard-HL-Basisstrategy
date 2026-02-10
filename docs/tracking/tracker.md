# Delta Neutral Bot - Implementation Tracker

**Project:** Asgard + Hyperliquid Delta Neutral Funding Rate Arbitrage Bot  
**Spec:** [docs/specs/spec.md](../specs/spec.md) (v3.5 - Custom Privy Auth Flow)  
**Strategy:** Equal Leverage Delta Neutral (2-4x, default 3x)  
**Deployment:** Single-tenant Docker with Privy embedded wallets  
**Auth:** Privy Email-Only with Custom Modals (v3.5)  
**UX:** Connect → Email → OTP → Deposit (new users) → Dashboard

---

## AGENT TODO LIST

> **For Future Agents:** This is your source of truth. Each section maps to [docs/specs/spec.md](../specs/spec.md). 
> 
> **Status Legend:**
> - `[x]` **BUILT** - Fully implemented and tested
> - `[~]` **PARTIAL** - Started but incomplete  
> - `[ ]` **NOT BUILT** - Not started, ready for implementation
> - `[!]` **BLOCKED** - Cannot proceed, needs resolution

---

## CORE ENGINE (BUILT) ✅

The core trading engine is **COMPLETE** with 957 tests passing. This was built in Phases 1-8 (pre-SaaS). DO NOT MODIFY unless fixing bugs.

### ✅ Phase 1: Project Setup

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Project structure | `src/` directories | `[x]` | 17 passing |
| Dependencies | `requirements.txt` | `[x]` | - |
| Configuration | `src/config/settings.py` | `[x]` | - |
| Assets & risk params | `src/config/assets.py`, `src/config/risk.yaml` | `[x]` | - |
| Logging | `src/utils/logger.py` | `[x]` | - |
| Retry utilities | `src/utils/retry.py` | `[x]` | - |

### ✅ Phase 2: Core Models

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Enums (Asset, Protocol, Chain) | `src/models/common.py` | `[x]` | 48 passing |
| Funding models | `src/models/funding.py` | `[x]` | - |
| Opportunity model | `src/models/opportunity.py` | `[x]` | - |
| Position models | `src/models/position.py` | `[x]` | - |
| Chain clients (Solana/Arbitrum) | `src/chain/` | `[x]` | - |
| Outage detector | `src/chain/outage_detector.py` | `[x]` | - |

### ✅ Phase 3: Asgard Integration

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Asgard API client | `src/venues/asgard/client.py` | `[x]` | 58 passing |
| Market data & rates | `src/venues/asgard/` | `[x]` | - |
| Transaction state machine | `src/state/state_machine.py` | `[x]` | - |
| Transaction builder | `src/venues/asgard/transactions.py` | `[x]` | - |
| Position manager | `src/venues/asgard/manager.py` | `[x]` | - |

### ✅ Phase 4: Hyperliquid Integration

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Hyperliquid API client | `src/venues/hyperliquid/client.py` | `[x]` | 72 passing |
| Funding oracle | `src/venues/hyperliquid/` | `[x]` | - |
| EIP-712 signer | `src/venues/hyperliquid/signer.py` | `[x]` | - |
| Trading with retry logic | `src/venues/hyperliquid/trader.py` | `[x]` | - |

### ✅ Phase 5: Core Strategy

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Opportunity detector | `src/core/opportunity_detector.py` | `[x]` | 111 passing |
| Price consensus | `src/core/price_consensus.py` | `[x]` | - |
| Fill validator | `src/core/fill_validator.py` | `[x]` | - |
| Position manager | `src/core/position_manager.py` | `[x]` | - |
| Position sizer | `src/core/position_sizer.py` | `[x]` | - |
| LST correlation monitor | `src/core/lst_monitor.py` | `[x]` | - |

### ✅ Phase 6: Risk Management

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Risk engine | `src/core/risk_engine.py` | `[x]` | 153 passing |
| Pause controller | `src/core/pause_controller.py` | `[x]` | - |
| Circuit breakers | `src/core/risk_engine.py` | `[x]` | - |
| Transaction validator | `src/security/transaction_validator.py` | `[x]` | - |

### ✅ Phase 7: Main Bot Loop

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Bot runner | `src/core/bot.py` | `[x]` | 45 passing |
| State persistence | `src/state/persistence.py` | `[x]` | - |
| Recovery on startup | `src/state/persistence.py` | `[x]` | - |

### ✅ Phase 8: Testing & Deployment

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Integration tests | `tests/integration/` | `[x]` | 133 passing |
| Shadow trading mode | `src/core/shadow.py` | `[x]` | - |
| Docker setup | `docker/` | `[x]` | - |
| Deployment scripts | `scripts/` | `[x]` | - |

---

## SAAS MIGRATION (IN PROGRESS) 🚧

### 🚧 Section 3: Authentication & Encryption [CRITICAL]

#### 3.1 Core Security (BUILT) ✅

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Encryption module** | `src/security/encryption.py` | `[x]` | AES-256-GCM + HMAC ✅ |
| **Server-secret KEK** | `src/dashboard/auth.py` | `[x]` | HMAC(user_id, server_secret) ✅ |
| **CSRF protection** | `src/dashboard/auth.py` | `[x]` | Token validation ✅ |
| **Session cookies** | `src/dashboard/auth.py` | `[x]` | HTTP-only, Secure ✅ |

#### 3.2 New Privy Auth Flow (v3.5) [BUILT] ✅

> **v3.5 Update:** New custom modal-based authentication with email-only login, inline OTP, and deposit modal. See [PRIVY_AUTH_SPEC.md](../PRIVY_AUTH_SPEC.md) for full specification.

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Users table migration** | `migrations/004_users_table.sql` | `[x]` | Store wallet addresses, email, is_new_user ✅ |
| **Privy JS SDK integration** | `templates/dashboard.html` | `[x]` | Using server-side auth via privy-python-sdk ✅ |
| **Connect button** | `templates/dashboard.html` | `[x]` | Header "Connect" button ✅ |
| **Email modal** | `templates/dashboard.html` | `[x]` | Custom email entry modal (Image 3 style) ✅ |
| **OTP modal** | `templates/dashboard.html` | `[x]` | 6-digit code entry (Image 4 style) ✅ |
| **Deposit modal** | `templates/dashboard.html` | `[x]` | New user deposit with QR codes (both chains) ✅ |
| **QR code generation** | `templates/dashboard.html` | `[x]` | Client-side QR generation via CDN ✅ |
| **POST /auth/privy/initiate** | `src/dashboard/api/auth.py` | `[x]` | Start auth, return session ✅ |
| **POST /auth/privy/verify** | `src/dashboard/api/auth.py` | `[x]` | Verify OTP, create user if new ✅ |
| **POST /auth/logout** | `src/dashboard/api/auth.py` | `[x]` | Clear session cookie ✅ |
| **GET /auth/me** | `src/dashboard/api/auth.py` | `[x]` | Return user + wallet addresses ✅ |
| **Wallet creation** | `src/dashboard/api/auth.py` | `[x]` | Auto-create Solana + EVM on signup ✅ |
| **Balance checker** | `src/dashboard/api/balances.py` | `[x]` | Check on-chain balances ✅ |
| **Session middleware** | `src/dashboard/middleware.py` | `[~]` | Validate JWT, attach user (using existing auth) |
| **Header state management** | `templates/dashboard.html` | `[x]` | Connect → Deposit + Settings dropdown ✅ |
| **"Stay logged in" option** | `templates/dashboard.html` | `[x]` | 7 days vs 24 hours session ✅ |
| **Rate limiting** | `src/dashboard/api/auth.py` | `[x]` | 5 OTP attempts per 15 min ✅ |
| **Email validation** | `src/dashboard/api/auth.py` | `[x]` | Format validation with pydantic ✅ |
| **Error handling** | `templates/dashboard.html` | `[x]` | Inline errors, shake animation ✅ |
| **Protected by Privy badge** | `templates/dashboard.html` | `[x]` | Footer badge on all modals ✅ |

**Auth Flow State Machine:**
```
[Connect] → [Email Modal] → [OTP Modal] → (New? → [Deposit Modal]) → [Dashboard]
                                              ↓
                                         (Existing? → Check Balance → [Dashboard or Deposit])
```

**Deposit Modal Requirements:**
- Display Solana address with QR code (Asgard)
- Display Arbitrum address with QR code (Hyperliquid)
- Full 42-character addresses with copy buttons
- "Go to Dashboard" button (skip deposit)
- Show for new users OR existing users with $0 balance

**Previous Auth (v3.3 and earlier):**
- Used Privy OAuth with Google/Twitter options
- Required redirect to Privy's hosted page
- **Status:** Replaced by new flow above | `[~]` Deprecated

---

### 🚧 Section 4: Setup Wizard + Dashboard [CRITICAL]

> **v3.4-v3.5 Update:** Dashboard is BUILT with 2-tab layout. Setup wizard being replaced by new auth flow.

#### 4.1 Old Setup Wizard (v3.4) [DEPRECATED]

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Step 1: Authentication** | `src/dashboard/setup/` | `[x]` | Old Privy OAuth - being replaced |
| **Step 2: Wallet Creation** | `src/dashboard/setup/` | `[x]` | Integrated into new auth flow |
| **Step 3: Exchange Config** | `src/dashboard/setup/` | `[x]` | Optional - can be done later |
| **Dashboard Access** | `src/dashboard/main.py` | `[x]` | Land on dashboard ✅ |

#### 4.2 Dashboard v2.0 (BUILT) ✅

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **FastAPI app** | `src/dashboard/main.py` | `[x]` | ✅ |
| **Home Tab** | `templates/dashboard.html` | `[x]` | ✅ |
| ├─ Leverage slider (2x-4x) | `templates/dashboard.html` | `[x]` | Real-time APY updates ✅ |
| ├─ Strategy Performance card | `templates/dashboard.html` | `[x]` | Net APY display ✅ |
| ├─ Asgard Leg details | `templates/dashboard.html` | `[x]` | SOL supply, USDC borrow ✅ |
| ├─ Hyperliquid Leg details | `templates/dashboard.html` | `[x]` | Funding rate ✅ |
| ├─ Quick Stats | `templates/dashboard.html` | `[x]` | Positions, PnL ✅ |
| ├─ Open Position button | `templates/dashboard.html` | `[x]` | Opens modal ✅ |
| └─ Active positions list | `templates/dashboard.html` | `[x]` | ✅ |
| **Settings Tab** | `templates/dashboard.html` | `[x]` | ✅ |
| ├─ 3 saveable presets | `templates/dashboard.html` | `[x]` | ✅ |
| ├─ Position settings | `templates/dashboard.html` | `[x]` | ✅ |
| ├─ Entry criteria | `templates/dashboard.html` | `[x]` | ✅ |
| └─ Risk management | `templates/dashboard.html` | `[x]` | ✅ |
| **Responsive Layout** | `templates/dashboard.html` | `[x]` | Desktop 2-col / Mobile tabs ✅ |

**Header State Change (IMPLEMENTED):**
```
BEFORE LOGIN:                    AFTER LOGIN:
┌──────────────────┐            ┌──────────────────────────┐
│     Connect      │     →      │  Deposit  [⚙️]           │
└──────────────────┘            └──────────────────────────┘
                                 Dropdown:
                                 - View Profile
                                 - Settings
                                 - Disconnect
```

#### 4.3 Dashboard Components Status

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Header - Before Login** | `templates/dashboard.html` | `[x]` | "Connect" button (top right) ✅ |
| **Header - After Login** | `templates/dashboard.html` | `[x]` | "Deposit" button + Settings ⚙️ ✅ |
| **Settings Dropdown** | `templates/dashboard.html` | `[x]` | View Profile, Settings, Disconnect ✅ |
| **🔴 FUND WALLETS button** | `templates/dashboard.html` | `[x]` | Part of new auth deposit modal ✅ |
| **🟢 OPEN POSITION button** | `templates/dashboard.html` | `[x]` | ✅ Working with job polling |
| **Real-time Rates** | `src/dashboard/api/rates.py` | `[x]` | ✅ Real Asgard + HL data |
| **Position Monitor** | `templates/dashboard.html` | `[x]` | ✅ Lists positions with PnL |
| **Job Status Polling** | `templates/dashboard.html` | `[x]` | ✅ Visual feedback on open |

---

### 🚧 Section 5: Position Management [IN PROGRESS]

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Open position (async job)** | `src/dashboard/api/positions.py` | `[x]` | ✅ Working end-to-end |
| **Job status polling** | `templates/dashboard.html` | `[x]` | ✅ Spinner → Checkmark/X |
| **Position list** | `templates/dashboard.html` | `[x]` | ✅ Shows active positions |
| **Close position** | `src/dashboard/api/positions.py` | `[x]` | Close position with async job ✅ |
| **Position PnL tracking** | `templates/dashboard.html` | `[x]` | Shows PnL, delta, health factor ✅ |
| **Position health** | `templates/dashboard.html` | `[x]` | Shows health status indicator ✅ |
| **Auto-liquidation alerts** | `templates/dashboard.html` | `[~]` | Health status shown, alerts TBD |

**Position Execution Flow (BUILT):**
```
Dashboard POST /api/v1/positions/open
    ↓
Create job in position_jobs table
    ↓
Background task _execute_position_job()
    ↓
BotBridge.open_position()
    ↓
Internal API /internal/positions/open
    ↓
OpportunityDetector (build opportunity)
    ↓
Preflight checks
    ↓
PositionManager.open_position()
    ↓
Asgard long → Hyperliquid short → Validation
    ↓
Update job status ← Dashboard polls /jobs/{job_id}
```

---

### 🚧 Section 6: Emergency Stop & Position Close [HIGH]

**Clarification:** Kill switches PAUSE the bot (stop new positions) but do NOT close existing positions. Manual position close works independently.

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **API pause/resume** | `src/dashboard/api/control.py` | `[x]` | ✅ Working - pauses bot operations |
| **File-based kill switch** | `src/core/kill_switch.py` | `[x]` | Pause bot via file trigger ✅ |
| **Manual position close** | `src/dashboard/api/positions.py` | `[x]` | ✅ Working - closes positions independently |
| **Docker stop handler** | `src/core/bot.py` | `[x]` | SIGTERM/SIGINT handlers ✅ |

---

### 🚧 Section 7: Real-Time Updates [MEDIUM]

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **SSE endpoint** | `src/dashboard/api/events.py` | `[x]` | Real-time updates via SSE ✅ |
| **Rate auto-refresh** | `templates/dashboard.html` | `[x]` | ✅ 30s polling working |
| **Position status SSE** | `src/dashboard/api/events.py` | `[x]` | position_opened/closed events ✅ |
| **PnL live updates** | `templates/dashboard.html` | `[x]` | Live PnL with toast notifications ✅ |

---

### 🚧 Section 8: Wallet & Balance Integration [CRITICAL]

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Fetch wallet balances** | `src/dashboard/api/balances.py` | `[x]` | Fetches SOL/USDC on Solana, ETH/USDC on Arbitrum ✅ |
| **Display SOL/USDC on Solana** | `templates/dashboard.html` | `[x]` | Shows in wallet balances section ✅ |
| **Display USDC on Arbitrum** | `templates/dashboard.html` | `[x]` | Shows in wallet balances section ✅ |
| **Insufficient funds warning** | `templates/dashboard.html` | `[x]` | Blocks Open Position button, shows alert ✅ |
| **Auto balance refresh** | `templates/dashboard.html` | `[x]` | Manual refresh button + fetch on auth ✅ |

---

### ✅ Section 9: Security Model [BUILT]

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Non-root Docker user** | `docker/Dockerfile` | `[x]` | Run as UID 1000 ✅ |
| **Read-only filesystem** | `docker/docker-compose.yml` | `[x]` | Read-only root, tmpfs for /tmp ✅ |
| **Capability dropping** | `docker/docker-compose.yml` | `[x]` | Drop ALL, no-new-privileges ✅ |
| **Localhost-only** | `src/dashboard/main.py` | `[x]` | ✅ |

---

### ✅ Section 11: Database Schema [BUILT]

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Schema version tracking** | `migrations/` | `[x]` | ✅ |
| **Migration system** | `src/db/migrations.py` | `[x]` | ✅ |
| **Config table** | `migrations/001_initial_schema.sql` | `[x]` | ✅ |
| **User keys table** | `migrations/001_initial_schema.sql` | `[x]` | ✅ |
| **Sessions table** | `migrations/001_initial_schema.sql` | `[x]` | ✅ |
| **Position jobs table** | `migrations/003_position_jobs.sql` | `[x]` | ✅ Async job tracking |

---

## COMPLETED ✅

### Core Engine (Phases 1-8)
- [x] All core trading components (957 tests passing)
- [x] Asgard + Hyperliquid integration
- [x] Risk engine + Circuit breakers
- [x] Position execution with async jobs
- [x] Docker + Deployment scripts

### Dashboard v2.0 (BUILT)
- [x] 2-tab layout (Home + Settings)
- [x] Responsive design (Desktop/Mobile)
- [x] Real-time APY calculator with leverage slider
- [x] Asgard + Hyperliquid leg detail panels
- [x] 3 saveable presets
- [x] Open Position with job polling
- [x] Real rate data from both exchanges
- [x] Position list display

### Backend APIs (BUILT)
- [x] `GET /api/v1/rates` - Real Asgard + HL rates
- [x] `GET /api/v1/settings` - Load/save settings
- [x] `POST /api/v1/positions/open` - Async position opening
- [x] `GET /api/v1/positions/jobs/{job_id}` - Job status polling
- [x] `POST /api/v1/control/pause|resume|emergency-stop`

### Documentation
- [x] GETTING_STARTED.md
- [x] README.md
- [x] spec.md (v3.5)
- [x] PRIVY_AUTH_SPEC.md

---

## PRIORITY QUEUE (Next to Implement)

### P0: Critical Path to Production
1. **Privy Auth Flow (v3.5)** ✅ COMPLETE
   - [x] Users table migration
   - [x] Email modal + OTP modal
   - [x] Deposit modal with QR codes
   - [x] Session management
   - [x] Connect → Deposit header transition

2. **Wallet Balance Integration** ✅ COMPLETE
   - [x] Fetch balances on login
   - [x] Display in dashboard
   - [x] Block trading if unfunded

### P1: High Priority
3. **Position Management** ✅ COMPLETE
   - [x] Close position button with confirmation modal
   - [x] Position PnL display in real-time
   - [x] Health status (healthy/at_risk) with color coding

4. **Emergency Stop** ✅ COMPLETE
   - [x] API pause/resume (pauses bot, keeps positions open)
   - [x] File-based kill switch (pause bot via filesystem)
   - [x] Manual position close (works even when bot paused)

### P2: Medium Priority
5. **Real-Time Updates** ✅ COMPLETE
   - [x] SSE endpoint at /api/v1/events/stream
   - [x] Position opened/closed notifications
   - [x] Dashboard toast notifications
   - [x] Auto-reconnect on disconnect

6. **Docker Hardening** ✅ COMPLETE
   - [x] Non-root user (UID 1000)
   - [x] Read-only root filesystem
   - [x] tmpfs for /tmp and cache
   - [x] Drop all capabilities
   - [x] no-new-privileges security option

---

## 📊 METRICS

| Metric | Value |
|--------|-------|
| Tests Passing | 1007 |
| Test Coverage | ~85% |
| Dashboard Tabs | 2 (Home + Settings) |
| Supported Asset | SOL/USDC only |
| Supported Venues | 2+ (Kamino, Drift) |
| Leverage Range | 2x - 4x |
| Async Job System | ✅ |
| Real Rates Data | ✅ |
| Position Execution | ✅ |
| Responsive Layout | ✅ |

---

## 🔴 TRUE MULTI-TENANT SAAS - ARCHITECTURE GAPS

> **DISCOVERY (2026-02-10):** Current implementation is **multi-user auth + single-tenant execution** (hybrid).  
> This section tracks the gaps to achieve true multi-tenant SaaS.

### Current State vs Target

| Layer | Current | Target | Status |
|-------|---------|--------|--------|
| **Authentication** | Multi-user (Privy) | Multi-user (Privy) | ✅ DONE |
| **User Data** | Per-user wallets/settings | Per-user wallets/settings | ✅ DONE |
| **Position Storage** | Global single-tenant | Per-user scoped | 🔴 CRITICAL GAP |
| **Bot Execution** | Single bot loop | Per-user or multi-tenant | 🔴 CRITICAL GAP |
| **Settings Storage** | Global config | Per-user scoped | 🔴 GAP |
| **Database** | SQLite | PostgreSQL + row-level security | 🟡 FUTURE |
| **Billing** | Not implemented | Usage tracking + plans | 🟡 FUTURE |

### Critical Issues Found

#### 1. Database Foreign Key Bug [CRITICAL] 🔴

**File:** `migrations/003_position_jobs.sql` line 22  
**Bug:**
```sql
FOREIGN KEY (user_id) REFERENCES users(user_id)  -- WRONG COLUMN NAME
```
**Fix:**
```sql
FOREIGN KEY (user_id) REFERENCES users(id)       -- CORRECT
```

**Impact:** Database constraint errors when creating position jobs.  
**Solution Options:**
- Create migration `005_fix_position_jobs_fk.sql` to drop and recreate FK
- Or patch `003_position_jobs.sql` if no prod data yet

#### 2. Single-Tenant Position Storage [CRITICAL] 🔴

**File:** `src/core/bot.py` line 168  
**Current:**
```python
self._positions: Dict[str, CombinedPosition] = {}  # Global for ALL users
```
**Required for SaaS:**
```python
self._positions: Dict[str, Dict[str, CombinedPosition]] = {}  # user_id -> positions
```

**Impact:** All users see same positions, position IDs collide.  
**Effort:** 3-5 days

#### 3. Single Bot Execution Loop [CRITICAL] 🔴

**File:** `src/core/bot.py`  
**Current:** One bot instance monitors all opportunities.  
**Required for SaaS:** Either:
- Option A: Per-user bot instances (simpler, higher resource usage)
- Option B: Multi-tenant scheduler with user-scoped execution

**Effort:** 1-2 weeks

### SaaS Migration Tasks

#### Phase 1: Critical Bug Fixes (Before Production)

| Task | Location | Status | Effort |
|------|----------|--------|--------|
| Fix FK bug in migration 003 | `migrations/005_fix_position_jobs_fk.sql` | `[ ]` | 2 hours |
| Add user_id to positions table | `migrations/` | `[ ]` | 4 hours |
| Refactor position storage | `src/core/bot.py` | `[ ]` | 3-5 days |
| Update all position queries | `src/dashboard/api/positions.py` | `[ ]` | 2 days |

#### Phase 2: Per-User Bot Execution

| Task | Location | Status | Effort |
|------|----------|--------|--------|
| Design per-user bot scheduler | `src/core/scheduler.py` | `[ ]` | 2 days |
| Implement user-scoped bot instances | `src/core/bot.py` | `[ ]` | 1 week |
| Update dashboard to show per-user status | `templates/dashboard.html` | `[ ]` | 3 days |
| Add user bot lifecycle management | `src/core/scheduler.py` | `[ ]` | 3 days |

#### Phase 3: Settings Isolation

| Task | Location | Status | Effort |
|------|----------|--------|--------|
| Add user_id to config table | `migrations/` | `[ ]` | 4 hours |
| Create per-user settings class | `src/config/user_settings.py` | `[ ]` | 2 days |
| Migrate global settings to per-user | `src/dashboard/api/settings.py` | `[ ]` | 2 days |

#### Phase 4: Infrastructure (Future)

| Task | Location | Status | Effort |
|------|----------|--------|--------|
| Migrate to PostgreSQL | `src/db/` | `[ ]` | 1 week |
| Add row-level security policies | `migrations/` | `[ ]` | 2 days |
| Implement usage tracking | `src/billing/` | `[ ]` | 1 week |
| Add subscription plan limits | `src/billing/` | `[ ]` | 1-2 weeks |

### Deployment Model Decision

**Option A: Container-Per-User (Recommended for Now)**
```
User A → Container A (SQLite, single bot) → User A's positions only
User B → Container B (SQLite, single bot) → User B's positions only
```
- ✅ Perfect isolation
- ✅ Use current code as-is
- ✅ Simpler to debug
- ❌ Higher infra costs
- ❌ Slower onboarding

**Option B: True Multi-Tenant (Future)**
```
All Users → Single Container (PostgreSQL, multi-tenant scheduler)
```
- ✅ Lower infra costs
- ✅ Faster onboarding
- ✅ Easier to manage at scale
- ❌ Complex to implement
- ❌ Higher security requirements

### Recommendation

**Immediate (v3.5.1):**
1. Fix FK bug in migration 003
2. Deploy as container-per-user model
3. Add orchestrator to spin containers up/down

**Future (v4.0):**
- Implement true multi-tenant architecture only if scale demands it

---

## API ENDPOINTS REFERENCE

### Authentication (v3.5 - Built)
```
POST /api/v1/auth/privy/initiate     # Start email auth
POST /api/v1/auth/privy/verify       # Verify OTP code
POST /api/v1/auth/logout             # Clear session
GET  /api/v1/auth/me                 # Get user + wallets
```

### Dashboard (Built)
```
GET  /api/v1/rates?leverage={n}      # Real-time rates
GET  /api/v1/settings                # Load settings
POST /api/v1/settings                # Save settings
POST /api/v1/settings/reset          # Reset to defaults
```

### Positions (Built)
```
POST /api/v1/positions/open          # Open position (async)
GET  /api/v1/positions/jobs/{id}     # Job status
GET  /api/v1/positions               # List positions
```

### Control (Partial)
```
POST /api/v1/control/pause           # ✅ Working
POST /api/v1/control/resume          # ✅ Working
POST /api/v1/control/emergency-stop  # ~ Partial
```

### Balances (To Build)
```
GET  /api/v1/balances                # Get wallet balances
```

---

## REFERENCE

### Quick Commands

```bash
# Run tests
cd /Users/jo/Projects/BasisStrategy
source .venv/bin/activate
pytest tests/ -v

# Run dashboard
source .venv/bin/activate
uvicorn src.dashboard.main:app --reload --port 8080

# Run bot (headless)
python run_bot.py
```

### Environment Variables

```bash
# Required for auth
PRIVY_APP_ID=cm...
PRIVY_APP_SECRET=privy-app-secret-...
DASHBOARD_SESSION_SECRET=$(openssl rand -hex 32)
DASHBOARD_JWT_SECRET=$(openssl rand -hex 32)
ADMIN_API_KEY=$(openssl rand -hex 32)

# Optional
SOLANA_RPC_URL=https://...
ARBITRUM_RPC_URL=https://...
```

### User Flow (v3.5 - Implemented)

```
1. Click "Connect" in header
   ↓
2. Enter email → Submit
   ↓
3. Enter OTP code from email
   ↓
4. (New users) → Deposit modal with QR codes
   (Existing users) → Check balance → Dashboard
   ↓
5. Dashboard with Deposit button + Settings dropdown
   ↓
6. Fund wallets (if needed) → Click "Open Position"
   ↓
7. Monitor trades on dashboard
```

---

## CHANGE LOG

### v8.4 (2026-02-10)
- **SaaS Architecture Audit COMPLETE**
- Discovered critical gap: multi-user auth but single-tenant execution
- Documented foreign key bug in `migrations/003_position_jobs.sql` (user_id → id mismatch)
- Added new section: "True Multi-Tenant SaaS - Architecture Gaps"
- Created migration plan: Phase 1 (bug fixes), Phase 2 (per-user bots), Phase 3 (settings), Phase 4 (infra)
- Decision: Deploy as container-per-user initially, true multi-tenant as v4.0

### v8.3 (2026-02-10)
- **Code Cleanup COMPLETE**
- Removed duplicate `os` import in `src/dashboard/main.py`
- Removed unused `Decimal` import in `src/dashboard/bot_bridge.py`
- Removed unused `get_current_user` import in `src/dashboard/api/status.py`
- Removed redundant `asyncio` import in `src/dashboard/api/positions.py`
- Removed unused `List` import in `src/chain/solana.py`
- Deleted dead files: `run_bot.py` (deprecated), `src/venues/privy_client.py` (duplicate)
- Deleted empty modules: `src/dashboard/alerts/`, `src/dashboard/middleware/`
- Consolidated `Asset` and `Protocol` enums - single source of truth in `src/models/common.py`
- Deleted orphaned test: `tests/unit/venues/test_privy_client.py`
- All tests passing: 1007

### v8.2 (2026-02-10)
- **Privy Auth Flow (v3.5) COMPLETE**
- Implemented users table migration (004_users_table.sql)
- Built auth API endpoints: /auth/privy/initiate, /auth/privy/verify, /auth/logout, /auth/me
- Created auth modals: Email, OTP, Deposit (all in dashboard.html)
- Added Connect → Deposit + Settings header state transition
- Implemented rate limiting (5 attempts per 15 min)
- Added "Stay logged in" option (7 days vs 24 hours)
- Integrated QR code generation for wallet addresses
- Updated test count: 1009 passing

### v8.1 (2026-02-06)
- Updated to reflect v3.5 auth flow
- Consolidated duplicate sections
- Updated test count: 957 passing
- Updated metrics (SOL/USDC only)
- Added clear P0/P1/P2 priority queue

---

*Last Updated: 2026-02-10*  
*Tracker Version: 8.4 (SaaS Architecture Audit)*  
*Spec Reference: docs/specs/spec.md v3.5*  
*Auth Spec: docs/PRIVY_AUTH_SPEC.md*
