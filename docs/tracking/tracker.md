# Delta Neutral Bot - Implementation Tracker

**Project:** Asgard + Hyperliquid Delta Neutral Funding Rate Arbitrage Bot  
**Spec:** [docs/specs/spec.md](../specs/spec.md) (v3.5 - Custom Privy Auth Flow)  
**Strategy:** Equal Leverage Delta Neutral (3-4x, default 3x)  
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

The core trading engine is **COMPLETE** with 555 tests passing. This was built in Phases 1-8 (pre-SaaS). DO NOT MODIFY unless fixing bugs.

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

#### 3.2 New Privy Auth Flow (v3.5) [IN PROGRESS]

> **v3.5 Update:** New custom modal-based authentication with email-only login, inline OTP, and deposit modal. See [PRIVY_AUTH_SPEC.md](../PRIVY_AUTH_SPEC.md) for full specification.

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Users table migration** | `migrations/004_users_table.sql` | `[ ]` | Store wallet addresses, email, is_new_user |
| **Privy JS SDK integration** | `templates/dashboard.html` | `[ ]` | Add `@privy-io/privy-browser` CDN |
| **Connect button** | `templates/dashboard.html` | `[ ]` | Header "Connect" button |
| **Email modal** | `templates/auth.html` | `[ ]` | Custom email entry modal (Image 3 style) |
| **OTP modal** | `templates/auth.html` | `[ ]` | 6-digit code entry (Image 4 style) |
| **Deposit modal** | `templates/auth.html` | `[ ]` | New user deposit with QR codes (both chains) |
| **QR code generation** | `static/js/qrcode.min.js` | `[ ]` | Client-side QR generation |
| **POST /auth/privy/initiate** | `src/dashboard/api/auth.py` | `[ ]` | Start auth, return session |
| **POST /auth/privy/verify** | `src/dashboard/api/auth.py` | `[ ]` | Verify OTP, create user if new |
| **POST /auth/logout** | `src/dashboard/api/auth.py` | `[ ]` | Clear session cookie |
| **GET /auth/me** | `src/dashboard/api/auth.py` | `[ ]` | Return user + wallet addresses |
| **Wallet creation** | `src/dashboard/privy_client.py` | `[ ]` | Auto-create Solana + EVM on signup |
| **Balance checker** | `src/dashboard/api/balances.py` | `[ ]` | Check on-chain balances |
| **Session middleware** | `src/dashboard/middleware.py` | `[ ]` | Validate JWT, attach user |
| **Header state management** | `templates/dashboard.html` | `[ ]` | Connect → Deposit + Settings dropdown |
| **"Stay logged in" option** | `templates/auth.html` | `[ ]` | 7 days vs 24 hours session |
| **Rate limiting** | `src/dashboard/api/auth.py` | `[ ]` | 5 OTP attempts per 15 min |
| **Email validation** | `src/dashboard/api/auth.py` | `[ ]` | Format validation |
| **Error handling** | `templates/auth.html` | `[ ]` | Inline errors, shake animation |
| **Protected by Privy badge** | `templates/auth.html` | `[ ]` | Footer badge on all modals |

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

> **v3.4 Update:** Simplified to 3-step setup. Both exchanges work with wallet-based auth (no API keys required). Funding & Strategy are dashboard actions.

#### 4.1 Setup Wizard (3 Steps)

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Step 1: Authentication** | `src/dashboard/setup/` | `[x]` | Privy OAuth login ✅ |
| **Step 2: Wallet Creation** | `src/dashboard/setup/` | `[x]` | EVM + Solana wallets ✅ |
| **Step 3: Exchange Config** | `src/dashboard/setup/` | `[x]` | Optional API keys (wallet auth works) ✅ |
| **Dashboard Access** | `src/dashboard/main.py` | `[x]` | Land on dashboard ✅ |

**Step 3 Details:**
- Asgard: Public access (1 req/sec) or add API key for unlimited
- Hyperliquid: Wallet-based EIP-712 signatures (no key needed)

#### 4.2 Dashboard (Action Hub)

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Header - Before Login** | `templates/dashboard.html` | `[ ]` | "Connect" button (top right) |
| **Header - After Login** | `templates/dashboard.html` | `[ ]` | "Deposit" button + Settings ⚙️ |
| **Settings Dropdown** | `templates/dashboard.html` | `[ ]` | View Profile, Settings, Disconnect |
| **🔴 FUND WALLETS button** | `templates/dashboard.html` | `[ ]` | Opens funding modal/page |
| **🟢 LAUNCH STRATEGY button** | `templates/dashboard.html` | `[ ]` | Opens strategy config modal |
| **Trade Status Display** | `templates/components/` | `[ ]` | Bot status, positions, PnL |
| **Wallet Balances** | `templates/components/` | `[ ]` | Real-time balance display |
| **SSE Updates** | `src/dashboard/api/events.py` | `[ ]` | Real-time trade updates |

**Header State Change:**
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

**Dashboard Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [🔴 FUND WALLETS]                    [🟢 LAUNCH STRATEGY]  │
├─────────────────────────────────────────────────────────────┤
│  TRADE STATUS          │  WALLET BALANCES                   │
│  ┌─────────────────┐   │  EVM: 0.00 USDC                   │
│  │ Bot: STANDBY   │   │  Solana: 0.00 SOL / 0.00 USDC     │
│  │ Positions: 0   │   │                                    │
│  │ PnL 24h: $0.00 │   │  [Check Balances]                 │
│  └─────────────────┘   │                                    │
│                        │  ACTIVE POSITIONS                  │
│  FUNDING RATES         │  No active positions               │
│  SOL-PERP: -12.5%     │                                    │
│  jitoSOL: +8.3%       │  RECENT ACTIVITY                   │
│                        │  No recent activity                │
└─────────────────────────────────────────────────────────────┘
```

#### 4.3 Funding Flow (Button Action)

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Funding modal/page** | `templates/funding.html` | `[ ]` | Show wallet addresses |
| **Copy address buttons** | `templates/funding.html` | `[ ]` | One-click copy |
| **Balance checker** | `src/dashboard/api/` | `[ ]` | Real-time balance API |
| **Minimum requirements** | `templates/funding.html` | `[ ]` | Show what's needed |
| **"I'm Done" button** | `templates/funding.html` | `[ ]` | Return to dashboard |

#### 4.4 Strategy Launch Flow (Button Action)

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Strategy modal** | `templates/strategy.html` | `[ ]` | Risk preset selection |
| **Risk presets** | `templates/strategy.html` | `[ ]` | Conservative/Balanced/Aggressive |
| **Leverage selector** | `templates/strategy.html` | `[ ]` | 2x/3x/4x |
| **Max position size** | `templates/strategy.html` | `[ ]` | Input field |
| **Review & confirm** | `templates/strategy.html` | `[ ]` | Summary before start |
| **Start bot** | `src/dashboard/api/control.py` | `[ ]` | POST /api/v1/control/start |

**API Endpoints Needed:**
```python
# Setup (4 steps)
GET  /setup/status              # Current progress
GET  /setup/privy/auth          # Step 1: Show OAuth login
POST /setup/privy/callback      # Step 1: Handle auth
POST /setup/wallets             # Step 2: Create wallets
POST /setup/exchange            # Step 3: Configure APIs
GET  /                         # Step 4: Dashboard (landing)

# Dashboard Actions
GET  /dashboard                 # Main dashboard
GET  /dashboard/funding         # Funding page/modal
GET  /dashboard/strategy        # Strategy config modal
POST /api/v1/control/start      # Start bot trading
POST /api/v1/control/pause      # Pause bot
POST /api/v1/control/stop       # Stop bot

# Real-time
GET  /api/v1/events             # SSE for live updates
GET  /api/v1/status             # Bot status
GET  /api/v1/positions          # Current positions
GET  /api/v1/balances           # Wallet balances
```

---

### 🚧 Section 6: Emergency Stop [HIGH]

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **API emergency stop** | `src/dashboard/api/control.py` | `[ ]` | POST /api/v1/control/emergency-stop |
| **File-based kill switch** | `src/core/kill_switch.py` | `[ ]` | Monitor /data/emergency.stop |
| **Docker stop handler** | `src/core/bot.py` | `[ ]` | SIGTERM graceful shutdown |

---

### 🚧 Section 8: Dashboard & API [CRITICAL]

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **FastAPI app** | `src/dashboard/main.py` | `[x]` | ✅ |
| **Dashboard UI** | `templates/dashboard.html` | `[ ]` | **FOCUS HERE** |
| **Top ribbon buttons** | `templates/dashboard.html` | `[ ]` | FUND + LAUNCH |
| **Trade status display** | `templates/components/` | `[ ]` | Cards with status |
| **Wallet balance display** | `templates/components/` | `[ ]` | Real-time balances |
| **Position list** | `templates/components/` | `[ ]` | Active positions |
| **SSE endpoint** | `src/dashboard/api/events.py` | `[ ]` | Live updates |
| **Bot control APIs** | `src/dashboard/api/control.py` | `[~]` | Start/pause/stop |

---

### 🚧 Section 9: Security Model [HIGH]

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Non-root Docker user** | `docker/Dockerfile` | `[ ]` | Run as UID 1000 |
| **Read-only filesystem** | `docker/docker-compose.yml` | `[ ]` | Except /data |
| **Localhost-only** | `src/dashboard/main.py` | `[x]` | ✅ |

---

### 🚧 Section 11: Database Schema [BUILT] ✅

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Schema version tracking** | `migrations/` | `[x]` | ✅ |
| **Migration system** | `src/db/migrations.py` | `[x]` | ✅ |
| **Config table** | `migrations/001_initial_schema.sql` | `[x]` | ✅ |
| **User keys table** | `migrations/001_initial_schema.sql` | `[x]` | ✅ |
| **Sessions table** | `migrations/001_initial_schema.sql` | `[x]` | ✅ |

---

## PRIORITY QUEUE

## ✅ COMPLETED

### Setup & Auth (v3.4 and earlier)
- [x] Server-secret KEK derivation (HMAC)
- [x] Encryption module (AES-256-GCM)
- [x] CSRF protection
- [x] Session cookies (HTTP-only, Secure)
- [x] 3-step wizard (Auth → Wallets → Exchange)
- [x] Optional API keys (wallet auth works without)
- [~] **Privy OAuth login (v3.3)** - Being replaced by new email-only flow

### 🚧 NEW: Privy Email Auth (v3.5) - Implementation Queue
- [ ] Users table migration
- [ ] Privy JS SDK integration
- [ ] Email modal (custom UI)
- [ ] OTP modal (6-digit inline)
- [ ] Deposit modal (QR codes for both chains)
- [ ] Connect → Deposit header transition
- [ ] Settings dropdown menu
- [ ] Session duration (7 days / 24 hours)
- [ ] Rate limiting (5 OTP / 15 min)

### Dashboard v2.0 - 2 Tab Layout
- [x] **Home Tab**
  - [x] Leverage slider (2x-4x) with real-time rate updates
  - [x] Asgard rates: SOL, jitoSOL, jupSOL, INF on Kamino/Drift
  - [x] Hyperliquid funding rates
  - [x] Active positions list
  - [x] Quick stats (PnL, position count)
  - [x] Open Position modal with job status polling
- [x] **Settings Tab**
  - [x] 3 saveable presets with descriptions
  - [x] Position settings (leverage, size limits)
  - [x] Entry criteria (min APY, volatility)
  - [x] Risk management (thresholds, toggles)
  - [x] Reset defaults button
- [x] **Funding Page** - Wallet addresses with copy buttons

### Backend APIs
- [x] `GET /api/v1/rates` - Asgard + Hyperliquid rates (real data!)
- [x] `GET /api/v1/settings` - Load settings
- [x] `POST /api/v1/settings` - Save settings
- [x] `POST /api/v1/settings/reset` - Reset defaults
- [x] `POST /api/v1/positions/open` - Open position (async job)
- [x] `GET /api/v1/positions/jobs/{job_id}` - Job status polling
- [x] `POST /api/v1/positions` - List positions
- [x] `POST /api/v1/control/pause|resume|emergency-stop`

### Position Execution (MVP Trading)
- [x] Migration: `position_jobs` table for async tracking
- [x] Internal API: `/internal/positions/open` endpoint
- [x] BotBridge: `open_position()` method
- [x] Dashboard API: Async job flow with background execution
- [x] Opportunity builder from simple params (asset, leverage, size)
- [x] Auto protocol selection (best APY) with user override
- [x] Preflight checks before execution
- [x] Full PositionManager integration (Asgard → Hyperliquid → Validation)
- [x] Job status polling UI with stage tracking

### Documentation
- [x] GETTING_STARTED.md - 3-minute quick start
- [x] README.md - Updated with new flow
- [x] spec.md - v3.4 with 2-tab dashboard

---

## ✅ COMPLETED (continued)

### Real Data Integration (No API Keys Needed!)
- [x] Wire up `/api/v1/rates` to fetch **real** Asgard market data (public endpoint, 1 req/sec)
- [x] Wire up `/api/v1/rates` to fetch **real** Hyperliquid funding rates (public)

**Completed:**
- ✅ `AsgardClient.get_markets()` works without API key (1 req/sec public access)
- ✅ Returns real net APY for SOL, jitoSOL, jupSOL, INF on Kamino/Drift/Marginfi/Solend
- ✅ `HyperliquidFundingOracle.get_current_funding_rates()` uses public endpoints
- ✅ Returns real SOL-PERP funding rates (annualized)
- ✅ Fixed `funding_oracle.py` to handle Hyperliquid's list response format `[meta, assetCtxs]`
- ✅ Dashboard shows loading states while fetching
- ✅ 555 tests passing

**Sample Real Data:**
```
Asgard SOL @ 3x: marginfi=-21.76%, kamino=-24.83%, drift=-31.58%
Hyperliquid SOL-PERP @ 3x: funding=-0.0195%, annualized=-21.34%
```

---

## 🚧 NEXT UP

### 1. Wallet Integration
- [ ] Fetch real wallet balances from Privy
- [ ] Display SOL/USDC on Solana
- [ ] Display USDC on Arbitrum
- [ ] Show "insufficient funds" warnings before opening positions

### 2. Position Management
- [ ] Close position button
- [ ] Position PnL tracking
- [ ] Position health monitoring
- [ ] Auto-liquidation warnings

### 3. Polish
- [ ] Emergency stop file-based kill switch
- [ ] Docker hardening (non-root, read-only fs)
- [ ] Alerting/monitoring webhooks

---

## 📊 METRICS

| Metric | Value |
|--------|-------|
| Tests Passing | 555 |
| Dashboard Tabs | 2 (Home + Settings) |
| Setup Steps | 3 |
| Saveable Presets | 3 |
| Supported Assets | 4 (SOL, jitoSOL, jupSOL, INF) |
| Supported Venues | 4 (Kamino, Drift, Marginfi, Solend) |
| Async Job System | ✅ |
| Real Rates Data | ✅ |
| Position Execution | ✅ |
- [x] Wire up `/api/v1/positions/open` to actually execute trades
- [x] Integrate with `PositionManager.open_position()`
- [x] Execute on Asgard (Solana long) via Privy signing
- [x] Execute on Hyperliquid (Arbitrum short) via EIP-712 signing
- [x] Store position in database
- [x] Update position list in real-time

**Implementation:**
- ✅ Migration `003_position_jobs.sql` - Async job tracking table
- ✅ `internal_api.py` - `/internal/positions/open` endpoint
  - Builds `ArbitrageOpportunity` from simple params
  - Auto-selects best protocol or uses user override
  - Runs preflight checks synchronously
  - Executes via `PositionManager.open_position()`
  - Returns structured result with position_id or error details
- ✅ `bot_bridge.py` - `open_position()` method to call internal API
- ✅ `positions.py` - Async job flow
  - `POST /open` creates job, triggers background execution
  - `GET /jobs/{job_id}` poll for status
  - `GET /jobs` list recent jobs
- ✅ Dashboard JavaScript - Job status polling with visual feedback
  - Shows spinner with current stage (market_data, preflight, asgard_open, etc.)
  - Updates to checkmark on success, X on failure
  - Auto-refreshes positions list on completion

**API Flow:**
```
Dashboard POST /open
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

**555 tests passing**

### 2. Wallet Integration
- [ ] Fetch real wallet balances from Privy
- [ ] Display SOL/USDC on Solana
- [ ] Display USDC on Arbitrum
- [ ] Show "insufficient funds" warnings

### 3. Position Management
- [ ] Close position button
- [ ] Position PnL tracking
- [ ] Position health monitoring
- [ ] Auto-liquidation warnings

### 2. Position Execution
- [ ] Wire up `/api/v1/positions/open` to actual bot
- [ ] Execute trades on Asgard + Hyperliquid
- [ ] Track position state in database

### 3. Real-time Updates (SSE)
- [ ] Live rate updates every 30s
- [ ] Position status changes
- [ ] PnL updates

### 4. Polish
- [ ] Emergency stop file-based kill switch
- [ ] Docker hardening (non-root, read-only fs)
- [ ] Alerting/monitoring webhooks

---

## 📊 METRICS

| Metric | Value |
|--------|-------|
| Tests Passing | 555 |
| Dashboard Tabs | 2 (Home + Settings) |
| Setup Steps | 3 |
| Saveable Presets | 3 |
| Supported Assets | 4 (SOL, jitoSOL, jupSOL, INF) |
| Supported Venues | 2+ (Kamino, Drift, +more) |

---

## REFERENCE

### Quick Commands

```bash
# Run tests
pytest tests/ -v

# Run dashboard
cd /Users/jo/Projects/BasisStrategy
source .venv/bin/activate
PYTHONPATH=/Users/jo/Projects/BasisStrategy uvicorn src.dashboard.main:app --reload --port 8080
```

### Environment (Operator Configured)

```bash
PRIVY_APP_ID=cm...
PRIVY_APP_SECRET=privy-app-secret-...
DASHBOARD_SESSION_SECRET=$(openssl rand -hex 32)
DASHBOARD_JWT_SECRET=$(openssl rand -hex 32)
ADMIN_API_KEY=$(openssl rand -hex 32)
```

### User Flow (v3.4 - Simplified)

```
1. Click "Login with Privy" → Authenticate
2. Wallets auto-created → Display addresses  
3. Optional: Add API keys for higher rate limits → Skip if unsure
4. Land on Dashboard
   ├─ Click 🔴 FUND WALLETS → Deposit funds → Return
   └─ Click 🟢 LAUNCH STRATEGY → Configure → Start bot
5. Monitor trades on dashboard
```

**Key Simplifications:**
- No API keys required (both exchanges use wallet auth)
- 3-step wizard instead of 6
- Setup time: ~3 minutes

---

*Last Updated: 2026-02-06*  
*Tracker Version: 8.1 (Privy Custom Auth Flow)*  
*Spec Reference: docs/specs/spec.md v3.5*
*Auth Spec: docs/PRIVY_AUTH_SPEC.md*
