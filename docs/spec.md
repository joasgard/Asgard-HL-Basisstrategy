# Asgard Basis - Technical Specification v4.0

**Product**: Asgard Basis
**Deployment Model**: Multi-user SaaS with Per-User Trading Contexts
**Wallet Infrastructure**: Privy Embedded Wallets (server-side signing)
**Authentication**: Privy Email-Only with Embedded Wallet Creation
**Primary Interface**: React SPA Dashboard served by FastAPI
**Database**: PostgreSQL 16 with asyncpg + Redis 7
**Version**: 4.0 (Multi-User SaaS)

> **Architecture Summary:**
>
> - Multiple users authenticate via Privy (email + OTP)
> - Each user has their own Privy-managed wallets (Solana + EVM)
> - Positions are scoped per-user via `UserTradingContext`
> - Background services (IntentScanner, PositionMonitor) manage all users
> - PostgreSQL for persistence, Redis for caching/locking/events
> - FastAPI backend serves React SPA + JSON API

---

## 1. Executive Summary

A delta-neutral funding rate arbitrage system supporting multiple users. Each user authenticates via Privy, receives embedded wallets, and can open/close positions through a React dashboard. Background services monitor positions and execute intent-based entries across all users.

### Strategy Overview

```
+-----------------------------------------------------------------+
|                    ASGARD (Solana)                                |
|  +-----------------------------------------------------------+  |
|  |  LONG Spot Margin Position                                 |  |
|  |  - Asset: SOL or SOL LST (jitoSOL, jupSOL, INF)           |  |
|  |  - Direction: LONG                                         |  |
|  |  - Leverage: 1.1-4x (default 3x)                          |  |
|  |  - Protocol: Best rate from Kamino/Drift                   |  |
|  +-----------------------------------------------------------+  |
+----------------------------+------------------------------------+
                             | Delta Neutral (Equal Leverage)
+----------------------------v------------------------------------+
|               HYPERLIQUID (Arbitrum)                              |
|  +-----------------------------------------------------------+  |
|  |  SHORT Perpetual Position                                  |  |
|  |  - Asset: SOL-PERP (SOLUSD)                                |  |
|  |  - Leverage: 1.1-4x (matches long side)                    |  |
|  |  - Funding: Received hourly (1/8 of 8hr rate)              |  |
|  +-----------------------------------------------------------+  |
+------------------------------------------------------------------+
```

**Yield Formula**: Hyperliquid funding earned - Asgard net borrowing cost + LST staking yield

---

## 2. Architecture

### 2.1 System Architecture

```
+--------------------------------------------------------------------+
|                     USER BROWSER                                    |
|  +-------------------+  +-------------------+  +----------------+  |
|  |  React SPA        |  |  Privy SDK        |  |  SSE Client    |  |
|  |  (Vite + TS)      |  |  (Auth + Wallets) |  |  (Real-time)   |  |
|  +-------------------+  +-------------------+  +----------------+  |
+-------------------------------+------------------------------------+
                                | HTTPS
+-------------------------------v------------------------------------+
|              NGINX REVERSE PROXY (Production)                      |
|  - TLS termination                                                 |
|  - Rate limiting                                                   |
|  - Static file serving                                             |
+-------------------------------+------------------------------------+
                                |
+-------------------------------v------------------------------------+
|              FastAPI BACKEND (backend/dashboard/)                   |
|  +-------------------------------------------------------------+  |
|  |  API Routers (/api/v1/*)                                     |  |
|  |  - auth, positions, intents, balances, rates                 |  |
|  |  - settings, control, events (SSE), status                   |  |
|  +-------------------------------------------------------------+  |
|  |  Middleware Stack                                             |  |
|  |  - Request ID, Logging, Security Headers, Rate Limiting      |  |
|  +-------------------------------------------------------------+  |
|  |  Background Services                                         |  |
|  |  - PositionMonitorService (30s cycle)                        |  |
|  |  - IntentScanner (60s cycle)                                 |  |
|  +-------------------------------------------------------------+  |
|  |  React SPA Serving (frontend/dist/)                          |  |
|  +-------------------------------------------------------------+  |
+------+---------+----------+----------+----------+------------------+
       |         |          |          |          |
       v         v          v          v          v
+----------+ +-------+ +--------+ +---------+ +----------+
| PostgreSQL| | Redis | | Privy  | | Asgard  | | Hyper-   |
| 16        | | 7     | | API    | | Finance | | liquid   |
| (asyncpg) | | Cache | | (Auth  | | (Solana)| | (Arb)   |
| Positions,| | Locks | |  + MPC | |         | |          |
| Users,    | | Events| |  Sign) | |         | |          |
| Intents   | | Rate  | |        | |         | |          |
+----------+ | Limit | +--------+ +---------+ +----------+
             +-------+
```

### 2.2 Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Database** | PostgreSQL 16 + asyncpg | Multi-tenant, JSONB support, connection pooling |
| **Cache/Events** | Redis 7 | Pub/sub for SSE, distributed locks, rate limiting |
| **Wallets** | Privy embedded | No private keys locally, TEE-backed MPC signing |
| **Frontend** | React + Vite + TypeScript + Tailwind | Modern SPA, component-based, type-safe |
| **Backend** | FastAPI + Pydantic | Async-first, auto-docs, validation |
| **Auth** | Privy Email + OTP | No passwords, auto wallet creation |
| **Multi-tenant** | UserTradingContext per user | Each user gets isolated exchange clients |
| **Entry Logic** | Intent-based | User submits criteria, bot waits for conditions |
| **Monitoring** | PositionMonitorService | Background service checks all users' positions |
| **Error Handling** | Structured error codes | Category-based codes (e.g., ASG-0001, HLQ-0003) |

### 2.3 Package Structure

The codebase is organized into three Python packages plus a React frontend:

```
AsgardBasis/
+-- bot/                  # Trading engine (core logic, venues, state)
|   +-- core/             # Bot orchestrator, risk engine, position management
|   |   +-- errors/       # Structured error codes and exception handlers
|   |   +-- bot.py        # Main bot loop
|   |   +-- intent_scanner.py      # Intent-based entry service
|   |   +-- position_monitor.py    # Multi-tenant exit monitor
|   |   +-- position_manager.py    # Entry/exit orchestration
|   |   +-- position_sizer.py      # Position sizing logic
|   |   +-- opportunity_detector.py # Opportunity scanning
|   |   +-- price_consensus.py     # Cross-venue price validation
|   |   +-- fill_validator.py      # Fill quality checks
|   |   +-- risk_engine.py         # Risk evaluation + circuit breakers
|   |   +-- kill_switch.py         # File-based emergency stop
|   |   +-- pause_controller.py    # Bot pause/resume
|   |   +-- lst_monitor.py         # LST correlation monitoring
|   |   +-- internal_api.py        # Bot's internal HTTP API
|   +-- venues/            # Exchange integrations
|   |   +-- user_context.py        # Per-user trading context factory
|   |   +-- asgard/                # Solana venue
|   |   |   +-- client.py          # Asgard API client
|   |   |   +-- manager.py         # Position management
|   |   |   +-- market_data.py     # Rate fetching
|   |   |   +-- transactions.py    # Transaction building
|   |   +-- hyperliquid/           # Arbitrum venue
|   |       +-- client.py          # Hyperliquid API client
|   |       +-- trader.py          # Order execution
|   |       +-- signer.py          # Privy-based EIP-712 signing
|   |       +-- funding_oracle.py  # Funding rate tracking
|   |       +-- depositor.py       # USDC bridge deposits
|   +-- state/             # State management
|       +-- persistence.py         # PostgreSQL persistence
|       +-- state_machine.py       # Position lifecycle FSM
|
+-- shared/               # Shared utilities (used by bot + backend)
|   +-- config/
|   |   +-- settings.py            # Pydantic settings (secrets loading)
|   |   +-- assets.py              # Supported assets config
|   |   +-- risk.yaml              # Risk limits & parameters
|   +-- db/
|   |   +-- database.py            # PostgreSQL async client (asyncpg)
|   |   +-- migrations.py          # Schema migration runner
|   +-- models/
|   |   +-- common.py              # Enums: Protocol, TransactionState, ExitReason
|   |   +-- position.py            # Position data models
|   |   +-- funding.py             # Funding rate models
|   |   +-- opportunity.py         # Arbitrage opportunity model
|   +-- chain/
|   |   +-- arbitrum.py            # Arbitrum RPC client
|   |   +-- solana.py              # Solana RPC client
|   |   +-- outage_detector.py     # Chain health monitoring
|   +-- security/
|   |   +-- encryption.py          # AES-256-GCM encryption
|   |   +-- transaction_validator.py
|   +-- common/
|   |   +-- schemas.py             # Pydantic request/response schemas
|   |   +-- events.py              # Event type definitions
|   +-- utils/
|   |   +-- logger.py              # Structured logging
|   |   +-- retry.py               # Retry with backoff
|   +-- redis_client.py            # Redis connection pooling
|
+-- backend/              # FastAPI dashboard application
|   +-- dashboard/
|       +-- main.py                # App factory + lifespan
|       +-- config.py              # DashboardSettings (Pydantic)
|       +-- auth.py                # Session management
|       +-- bot_bridge.py          # HTTP bridge to bot
|       +-- cache.py               # Stale-data caching
|       +-- events_manager.py      # SSE + Redis pub/sub
|       +-- privy_client.py        # Privy SDK wrapper
|       +-- security.py            # Security utilities
|       +-- dependencies.py        # FastAPI DI
|       +-- middleware/
|       |   +-- rate_limit.py      # Redis-backed rate limiting
|       +-- setup/
|       |   +-- steps.py           # Wallet setup steps
|       |   +-- validators.py      # Setup validation
|       |   +-- jobs.py            # Async job management
|       +-- api/                   # API route handlers
|           +-- auth.py            # Login/logout/session
|           +-- positions.py       # Position CRUD
|           +-- intents.py         # Intent CRUD
|           +-- balances.py        # Wallet balances
|           +-- rates.py           # Funding rates
|           +-- settings.py        # User settings
|           +-- control.py         # Bot control (pause/resume)
|           +-- events.py          # SSE event stream
|           +-- status.py          # Health checks
|           +-- wallet_setup.py    # Wallet provisioning
|
+-- frontend/             # React SPA
|   +-- src/
|   |   +-- App.tsx                # Main app (Privy + React Query)
|   |   +-- api/                   # API client layer
|   |   +-- components/
|   |   |   +-- auth/              # LoginPage (Privy LoginModal)
|   |   |   +-- dashboard/         # Dashboard view
|   |   |   +-- positions/         # Position cards, open/close modals
|   |   |   +-- settings/          # Settings view
|   |   |   +-- layout/            # Layout wrapper
|   |   |   +-- ui/                # Reusable UI components
|   |   |   +-- modals/            # Modal components
|   |   +-- hooks/                 # Custom React hooks (useAuth, useSSE)
|   |   +-- stores/                # State management
|   +-- vite.config.ts
|   +-- tailwind.config.js
|   +-- vitest.config.ts           # Unit tests
|   +-- playwright.config.ts       # E2E tests
|
+-- migrations/           # PostgreSQL migrations (8 files)
+-- docker/               # Dockerfile + docker-compose.yml
+-- docker-compose.prod.yml  # Production orchestration
+-- tests/                # Test suite
|   +-- unit/             # Unit tests by module
|   +-- integration/      # End-to-end integration tests
|   +-- fixtures/         # Test data
+-- run_dashboard.py      # Local development entry point
+-- requirements/         # Split requirements files
+-- secrets/              # API keys and secrets (git-ignored)
```

### 2.4 Wallet Infrastructure (Privy)

Privy provides non-custodial embedded wallets with TEE-backed MPC signing:

- Keys are **sharded** across user device, Privy server, and TEE enclave
- **TEE isolation**: Keys reconstituted only in secure hardware
- **No plaintext exposure**: Private key never in memory/logs
- **Non-custodial**: Privy cannot access keys without user shard
- **Exportable**: Users can export keys for self-custody anytime

**Wallet Creation:** On first login, the Privy SDK creates:
- Solana wallet (for Asgard positions)
- EVM wallet (for Hyperliquid via Arbitrum)

Both wallet addresses are stored in the `users` table (public info).

---

## 3. Authentication

### 3.1 Auth Flow (Privy Email + OTP)

```
User clicks "Connect" in React header
        |
        v
Privy LoginModal opens (email-only, dark theme)
        |
        v
User enters email --> Privy sends OTP
        |
        v
User enters 6-digit OTP --> Privy validates
        |
        v
Frontend calls POST /api/v1/auth/sync with Privy access token
        |
        v
Backend verifies token, creates/finds user in DB
        |
        v
Backend ensures wallets exist (Solana + EVM via Privy API)
        |
        v
JWT session cookie issued (httpOnly, Secure, SameSite)
        |
        v
New user? --> Check balance --> Show deposit modal if needed
Existing user? --> Go to dashboard
```

### 3.2 Encryption Architecture

Two-tier key hierarchy for field-level encryption:

| Layer | Purpose | Storage |
|-------|---------|---------|
| **KEK** (Key Encryption Key) | Derived from `HMAC_SHA256(privy_user_id, server_secret)` | Never persisted, in-memory only |
| **DEK** (Data Encryption Key) | Random 256-bit, encrypts sensitive config fields | PostgreSQL, encrypted by KEK |
| **Encrypted Fields** | API keys, auth keys | PostgreSQL, AES-256-GCM |

### 3.3 Auth API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/sync` | Sync Privy auth, create/find user, issue session |
| POST | `/api/v1/auth/logout` | Clear session cookie |
| GET | `/api/v1/auth/me` | Get current user + wallet addresses |

### 3.4 Security Measures

- **httpOnly Cookies**: Session token not accessible via JavaScript
- **CSRF Protection**: Token validation on state-changing requests
- **Rate Limiting**: Redis-backed, per-IP and per-user limits
- **Security Headers**: CSP, HSTS, X-Frame-Options, X-Content-Type-Options
- **Input Validation**: Pydantic models for all request bodies

---

## 4. Dashboard

### 4.1 React SPA Architecture

The dashboard is a React SPA served by FastAPI:

- **React + TypeScript + Vite** for the frontend build
- **Tailwind CSS** for styling
- **React Query** (`@tanstack/react-query`) for server state
- **Privy React SDK** for authentication
- **SSE** for real-time updates
- FastAPI serves the built SPA from `frontend/dist/` with client-side routing fallback

### 4.2 Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/` | Dashboard | Main view: rates, positions, wallet balances |
| `/positions` | Positions | Position list with open/close modals |
| `/settings` | Settings | Strategy configuration |

### 4.3 Key Components

- **Dashboard**: Leverage slider, Asgard/Hyperliquid rate panels, active positions list, open position button
- **OpenPositionModal**: Size input, leverage selection, balance validation
- **ClosePositionModal**: Confirmation dialog, async job tracking
- **PositionCard**: Position details with PnL, health factor, close button
- **LoginPage**: Privy LoginModal integration
- **Layout**: Navigation header with auth state (Connect/Deposit/Settings)

### 4.4 Real-Time Updates (SSE)

```
GET /api/v1/events/stream
```

Event types:
```
position_opened   -> New position created
position_closed   -> Position closed with PnL
position_update   -> PnL or health factor changed
rate_update       -> Funding rates updated
bot_status        -> Bot paused/resumed/connected
balance_update    -> Wallet balance changed
ping              -> Keepalive (every 30s)
error             -> Error notification
```

The event manager uses Redis pub/sub for multi-instance support.

---

## 5. API Endpoints

All endpoints are prefixed with `/api/v1/`.

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/sync` | Sync Privy auth, issue session |
| POST | `/auth/logout` | Clear session |
| GET | `/auth/me` | Current user + wallets |

### Positions
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/positions` | List user's positions |
| POST | `/positions/open` | Open position (async job) |
| POST | `/positions/{id}/close` | Close position (async job) |
| GET | `/positions/jobs/{job_id}` | Poll job status |

### Intents
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/intents` | Create position intent (with balance preflight) |
| GET | `/intents` | List user's intents (filter by status) |
| GET | `/intents/{id}` | Get intent details |
| DELETE | `/intents/{id}` | Cancel pending intent |

### Market Data
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/rates?leverage={n}` | Asgard + Hyperliquid rates at leverage |
| GET | `/balances` | Wallet balances (SOL, USDC on both chains) |
| GET | `/balances/check` | Preflight balance sufficiency check |

### Settings
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/settings` | Load user settings |
| POST | `/settings` | Save settings |
| POST | `/settings/reset` | Reset to defaults |

### Bot Control
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/control/pause` | Pause bot (stops new positions) |
| POST | `/control/resume` | Resume bot operations |
| POST | `/control/emergency-stop` | Emergency pause |

### Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/events/stream` | SSE event stream |
| GET | `/events/status` | Event system status |

### Wallet Setup
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/wallet-setup/ensure-wallets` | Ensure user has both wallets |

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health/live` | Liveness probe |
| GET | `/health/ready` | Readiness (DB + Redis + services) |

---

## 6. Core Trading Engine

### 6.1 Opportunity Detection

```python
class OpportunityDetector:
    ALLOWED_ASSETS = ["SOL", "jitoSOL", "jupSOL", "INF"]
    FUNDING_LOOKBACK_HOURS = 168  # 1 week

    async def scan(self) -> List[ArbitrageOpportunity]:
        """
        1. Fetch Asgard rates for all SOL/LST pairs
        2. Fetch Hyperliquid SOL-PERP funding
        3. Check both current AND predicted funding < 0
        4. Calculate total APY = |funding| + net_carry
        5. Filter: total APY > min_threshold
        """
```

### 6.2 Intent-Based Entry

Instead of immediate execution, users create **intents** with entry criteria:

```
User creates intent:
  - Asset: SOL
  - Size: $10,000
  - Leverage: 3x
  - Criteria: funding_rate < -5%, volatility < 50%
        |
        v
IntentScanner polls every 60s:
  1. Load all pending/active intents
  2. For each: check market conditions vs criteria
  3. If all criteria pass: execute via UserTradingContext
  4. If expired: mark as expired
        |
        v
On execution:
  - Creates UserTradingContext for the user
  - Opens Asgard long + Hyperliquid short
  - Updates intent status to "executed"
  - Links to resulting position
```

**Intent Criteria:**
- `min_funding_rate`: Funding rate must be below this (negative = shorts paid)
- `max_funding_volatility`: 1-week funding volatility must be below this
- `max_entry_price`: Current SOL price must be below this (optional)
- `expires_at`: Intent auto-cancels after this timestamp

### 6.3 Position Monitoring

The `PositionMonitorService` runs as a background task:

```
Every 30 seconds:
  1. Query all open positions (SELECT WHERE is_closed = 0)
  2. Group positions by user_id
  3. For each user's positions:
     a. Create UserTradingContext with their wallets
     b. Fetch live data from Hyperliquid + Asgard
     c. Update DB with current PnL, health factor, funding rate
     d. Run risk engine checks
  4. If exit conditions triggered:
     a. Close Hyperliquid short FIRST (reduce liquidation risk)
     b. Close Asgard long
     c. Archive to position_history
```

**Exit Triggers (priority order):**
1. Asgard health factor <= 10%
2. Hyperliquid margin fraction < 10%
3. Funding rate turns positive (shorts paying instead of earning)

### 6.4 Per-User Trading Context

```python
class UserTradingContext:
    """Per-user trading context for multi-tenant execution."""

    def __init__(self, user_id: str, solana_address: str, evm_address: str):
        self.user_id = user_id
        self.solana_address = solana_address
        self.evm_address = evm_address

    # Lazy initialization of exchange clients
    def get_hl_trader(self) -> HyperliquidTrader:
        """Hyperliquid trader with Privy signer for this user's EVM wallet."""

    def get_asgard_manager(self) -> AsgardPositionManager:
        """Asgard manager for this user's Solana wallet."""

    def get_hl_depositor(self) -> HyperliquidDepositor:
        """Handles USDC bridging from Arbitrum to Hyperliquid."""
```

### 6.5 Execution Flow

```
1. PRE-FLIGHT CHECKS
   +-- Price consensus check (< 0.5% deviation)
   +-- Wallet balance validation (per-user)
   +-- Fee market check (Solana priority fees)
   +-- Protocol capacity check
   +-- Simulate both legs

2. EXECUTE ASGARD LONG
   +-- Build: POST /create-position
   +-- Sign: Via Privy Solana API (user's wallet)
   +-- Submit: POST /submit-create-position-tx
   +-- Confirm: Poll /refresh-positions

3. EXECUTE HYPERLIQUID SHORT
   +-- Set leverage to match Asgard
   +-- Place market short order
   +-- Sign: Via Privy EVM API (EIP-712, user's wallet)
   +-- Confirm: Query clearinghouseState

4. POST-EXECUTION VALIDATION
   +-- Verify both positions confirmed
   +-- Check fill price deviation < 0.5%
   +-- Calculate actual delta
   +-- Store position in PostgreSQL (scoped to user)
```

### 6.6 Risk Management

```yaml
# shared/config/risk.yaml
risk_limits:
  # Position
  max_position_size_usd: 500000
  max_positions_per_asset: 1
  default_leverage: 3.0
  max_leverage: 4.0
  min_leverage: 1.1

  # Asgard
  min_health_factor: 0.20
  liquidation_proximity: 0.20

  # Hyperliquid
  margin_fraction_threshold: 0.10

  # Execution
  max_price_deviation: 0.005
  max_slippage_entry_bps: 50
  max_slippage_exit_bps: 100
  max_delta_drift: 0.005

  # Gas protection
  max_solana_priority_fee_sol: 0.01
  max_solana_emergency_fee_sol: 0.02

  # LST Monitoring
  lst_warning_premium: 0.03
  lst_critical_premium: 0.05
  lst_velocity_warning: 0.02
  lst_velocity_critical: 0.05
```

---

## 7. Error Handling

### 7.1 Error Code System

Structured error codes in `bot/core/errors/codes.py`:

**Format:** `XXX-NNNN` (3-letter category + 4-digit number)

| Category | Code | Description |
|----------|------|-------------|
| GEN | General | Unknown errors, timeouts, internal errors |
| VAL | Validation | Invalid input, leverage, size, asset |
| ASG | Asgard | API errors, tx failures, insufficient collateral |
| HLQ | Hyperliquid | API errors, margin issues, order failures |
| POS | Position | Not found, already closed, leg mismatch |
| RSK | Risk | Circuit breaker, max exposure, delta drift |
| WAL | Wallet | Balance insufficient, signing failed |
| NET | Network | RPC errors, chain outage |
| AUT | Auth | Invalid session, unauthorized |

**Examples:**
- `VAL-0003`: Leverage must be between 1.1x and 4x
- `ASG-0009`: Asgard health factor too low
- `HLQ-0003`: Insufficient margin on Hyperliquid
- `RSK-0005`: Circuit breaker triggered

### 7.2 Error Response Format

```json
{
  "error": {
    "code": "HLQ-0003",
    "message": "Insufficient margin on Hyperliquid",
    "category": "HYPERLIQUID",
    "http_status": 400
  },
  "request_id": "abc-123"
}
```

---

## 8. Emergency Stop

### 8.1 Kill Switch Options

| Method | Speed | Effect |
|--------|-------|--------|
| Docker stop | Immediate | Container stops, positions stay open |
| API pause | <1s | Bot pauses, positions stay open |
| File-based | 5s | Bot pauses via filesystem trigger |
| Manual close | 30-120s | Actually closes individual positions |

**Important:** Kill switches PAUSE the bot (stop new entries) but do NOT close positions. Positions must be closed manually via the dashboard or API.

### 8.2 Manual Position Close

Works even when bot is paused/stopped:
- Dashboard "Close" button on each position card
- `POST /api/v1/positions/{id}/close` API endpoint
- Creates async job, closes Hyperliquid short then Asgard long
- Status tracked via job polling

---

## 9. Database

### 9.1 Infrastructure

- **PostgreSQL 16** via asyncpg with connection pooling (min 2, max 10)
- **Automatic `?` to `$N` conversion** for SQLite compatibility during migration
- **Transaction support** via async context manager
- **Schema migrations** tracked with version + checksum

### 9.2 Migration Files

| Version | File | Purpose |
|---------|------|---------|
| 001 | `001_initial_schema.sql` | Core tables: config, positions, funding |
| 002 | `002_add_backup_and_positions.sql` | Backup tracking, position history |
| 003 | `003_position_jobs.sql` | Async job queue for position operations |
| 004 | `004_users_table.sql` | Multi-tenant users table |
| 005 | `005_add_user_scoped_positions.sql` | User-scoped positions with JSONB |
| 006 | `006_add_error_codes.sql` | Error code column on position_jobs |
| 007 | `007_position_intents.sql` | Intent-based entry system |
| 008 | `008_job_durability.sql` | Crash recovery (retry_count, last_error) |

### 9.3 Key Tables

```sql
-- Users (Privy-managed wallets)
CREATE TABLE users (
    id TEXT PRIMARY KEY,              -- Privy user ID
    email TEXT UNIQUE,
    solana_address TEXT,              -- Solana wallet address
    evm_address TEXT,                 -- EVM/Arbitrum wallet address
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_new_user BOOLEAN DEFAULT TRUE
);

-- User-Scoped Positions
CREATE TABLE positions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    data JSONB NOT NULL,              -- Full position data
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_closed INTEGER DEFAULT 0
);

-- Position Intents (intent-based entry)
CREATE TABLE position_intents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    asset TEXT DEFAULT 'SOL',
    leverage REAL DEFAULT 3.0,
    size_usd REAL NOT NULL,
    -- Entry criteria
    min_funding_rate REAL,
    max_funding_volatility REAL DEFAULT 0.50,
    max_entry_price REAL,
    -- Lifecycle
    status TEXT CHECK (status IN (
        'pending', 'active', 'executed', 'cancelled', 'expired', 'failed'
    )),
    position_id TEXT,
    job_id TEXT,
    execution_error TEXT,
    criteria_snapshot JSONB,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    executed_at TIMESTAMP
);

-- Async Job Queue
CREATE TABLE position_jobs (
    job_id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    job_type TEXT,                     -- 'open' or 'close'
    status TEXT,                       -- 'pending', 'running', 'completed', 'failed'
    result JSONB,
    error_code TEXT,                   -- Structured error code (e.g., HLQ-0003)
    last_error TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Configuration (field-level encryption)
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT,
    value_encrypted BYTEA,
    is_encrypted BOOLEAN DEFAULT FALSE
);
```

---

## 10. Deployment

### 10.1 Local Development

```bash
# Prerequisites: PostgreSQL + Redis running locally
python run_dashboard.py
# Starts: uvicorn backend.dashboard.main:app --reload --port 8080
```

### 10.2 Production (Docker Compose)

`docker-compose.prod.yml` orchestrates:

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| PostgreSQL 16 | postgres:16-alpine | 5432 | Database |
| Redis 7 | redis:7-alpine | 6379 | Cache, locks, events |
| App | Custom (uvicorn) | 8080 | FastAPI + React SPA |
| Nginx | nginx:alpine | 80/443 | Reverse proxy, TLS |

### 10.3 Docker Security Hardening

- **Non-root user**: `botuser` (UID 1000)
- **Read-only filesystem**: `read_only: true`
- **Capability dropping**: `cap_drop: ALL`, `no-new-privileges: true`
- **tmpfs mounts**: `/tmp` and cache directories
- **Resource limits**: CPU/memory caps
- **Health checks**: All services with interval/timeout/retries
- **Network isolation**: Internal bridge network

### 10.4 Startup Sequence

```
1. PostgreSQL ready (health check)
2. Redis ready (health check)
3. FastAPI lifespan begins:
   a. Connect to PostgreSQL
   b. Run database migrations
   c. Recover stuck jobs from previous crash
   d. Connect to Redis
   e. Start event manager (SSE + pub/sub)
   f. Start bot bridge
   g. Start PositionMonitorService (30s cycle)
   h. Start IntentScanner (60s cycle)
4. Serve API + React SPA
```

### 10.5 Graceful Shutdown

Reverse order: stop IntentScanner -> stop PositionMonitor -> stop bot bridge -> stop events -> release Redis locks -> close Redis -> close PostgreSQL.

---

## 11. Security Model

### 11.1 Infrastructure Security

- **Non-root containers** with minimal capabilities
- **Read-only root filesystem** (writable: /data, /logs, /tmp)
- **Network isolation**: Services on internal bridge network
- **Nginx reverse proxy**: TLS termination, rate limiting
- **No SSH**: No remote shell access to containers

### 11.2 Application Security

- **Privy wallets**: No private keys in the application
- **Field-level encryption**: AES-256-GCM for sensitive config
- **JWT sessions**: httpOnly, Secure, SameSite cookies
- **CSRF protection**: Token validation on mutations
- **Rate limiting**: Redis-backed, per-IP and per-user
- **Security headers**: HSTS, CSP, X-Frame-Options, etc.
- **Transaction validation**: Only allow known programs/actions
- **Structured logging**: JSON format, PII sanitized

### 11.3 Secrets Management

Required files in `secrets/` directory:

| File | Purpose |
|------|---------|
| `server_secret.txt` | Server secret for KEK derivation, JWT signing |
| `privy_app_id.txt` | Privy application ID |
| `privy_app_secret.txt` | Privy application secret |
| `privy_auth.pem` | EC private key for Privy server signing |
| `solana_rpc_url.txt` | Solana RPC endpoint |
| `arbitrum_rpc_url.txt` | Arbitrum RPC endpoint |
| `asgard_api_key.txt` | Asgard Finance API key |

All secrets loaded at startup, never stored in environment variables or version control.

---

## 12. Monitoring & Health

### 12.1 Health Endpoints

| Endpoint | Purpose | Checks |
|----------|---------|--------|
| `GET /health/live` | Liveness probe | Process alive |
| `GET /health/ready` | Readiness probe | DB + Redis + background services |

### 12.2 Background Service Health

The readiness endpoint reports status of:
- `database`: PostgreSQL connectivity
- `redis`: Redis connectivity
- `bot_connected`: Bot bridge reachable
- `position_monitor`: Running/stopped
- `intent_scanner`: Running/stopped

### 12.3 Logging

Structured JSON logging to stdout:
```json
{
  "timestamp": "2026-02-12T00:00:00",
  "level": "INFO",
  "logger": "backend.dashboard.main",
  "message": "request",
  "method": "GET",
  "path": "/api/v1/rates",
  "status": 200,
  "duration_ms": 45.2,
  "request_id": "abc-123"
}
```

---

## 13. Testing

### 13.1 Test Structure

```
tests/
+-- unit/
|   +-- core/           # Bot core logic tests
|   +-- config/         # Configuration tests
|   +-- security/       # Encryption, validation tests
|   +-- chain/          # Blockchain client tests
|   +-- dashboard/      # API endpoint tests
|   +-- venues/         # Exchange integration tests
+-- integration/        # End-to-end flow tests
+-- fixtures/           # Shared test data
```

### 13.2 Test Categories

| Category | Count | Tools |
|----------|-------|-------|
| Unit tests | ~1000+ | pytest, AsyncMock |
| Integration tests | ~130 | pytest-asyncio |
| Frontend unit | vitest | vitest |
| E2E | Configured | Playwright |

### 13.3 Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest --cov=. --cov-report=html

# Frontend tests
cd frontend && npm test
```

---

## 14. External API References

- **Asgard Finance**: https://github.com/asgardfi/api-docs
- **Hyperliquid**: https://hyperliquid.gitbook.io/hyperliquid-docs/
- **Privy**: https://docs.privy.io/

---

*Document Version: 4.0 (Multi-User SaaS)*
*Last Updated: 2026-02-12*

---

## Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| v4.0 | 2026-02-12 | Major rewrite: PostgreSQL+Redis, modular packages (bot/shared/backend), React SPA, intent system, position monitor, error codes, per-user trading contexts |
| v3.5.1 | 2026-02-10 | Added SaaS architecture gaps, FK bug documentation |
| v3.5 | 2026-02-10 | Custom Privy auth flow, email-only login |
| v3.4 | 2026-02-06 | Simplified 4-step wizard, 2-tab dashboard |
