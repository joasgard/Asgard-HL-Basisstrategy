# SaaS Migration Analysis

**Date:** 2026-02-05  
**Model:** Single-tenant Docker deployments with shared Privy infrastructure  
**Target:** Frontend-first onboarding, CLI as secondary

---

## Executive Summary

The current codebase is ~70% ready for SaaS. The core trading engine is solid, but significant work is needed around:
- User onboarding flow (wizard)
- Configuration management (UI-based, not file-based)
- User isolation (per-user state/secrets)
- Privy wallet creation flow

---

## 1. What's Already Built & Useful ✅

### Core Trading Engine (100% Reusable)
| Component | Status | Notes |
|-----------|--------|-------|
| `DeltaNeutralBot` | ✅ | Main orchestration - works as-is |
| `OpportunityDetector` | ✅ | Funding rate monitoring |
| `PositionManager` | ✅ | Position lifecycle management |
| `RiskEngine` | ✅ | Circuit breakers, risk limits |
| `PauseController` | ✅ | Emergency stops |
| `FillValidator` | ✅ | Trade validation |
| `PriceConsensus` | ✅ | Price validation |
| All venue clients | ✅ | Asgard, Hyperliquid integrations |

### Dashboard Foundation (70% Reusable)
| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI app structure | ✅ | Good foundation |
| JWT auth (`dashboard/auth.py`) | ✅ | Need to adapt for user auth flow |
| Bot bridge (`bot_bridge.py`) | ✅ | Works for single-bot-per-deployment |
| Jinja2 templates | ✅ | Need to add setup wizard pages |
| Static files | ✅ | CSS/JS already there |
| API endpoints | ✅ | `/api/v1/status`, `/api/v1/positions` |

### Infrastructure (100% Reusable)
| Component | Status | Notes |
|-----------|--------|-------|
| Privy integration | ✅ | `signer.py`, `transactions.py` |
| Settings system | ✅ | Just need UI wrapper |
| State persistence | ✅ | SQLite with aiosqlite |
| Retry logic | ✅ | `utils/retry.py` |
| Logging | ✅ | Structured logging |
| Docker setup | ✅ | `docker/` directory |

---

## 2. What's Built But Not Useful ❌

### Dashboard Components to Replace
| Component | Issue | Replacement |
|-----------|-------|-------------|
| `dashboard/auth.py` user mgmt | Loads from env/file, static users | Proper user registration/login flow |
| File-based config | Requires SSH/text editing | UI-based configuration wizard |
| `secrets/` directory | Manual setup | Privy wallet creation API |
| `ADMIN_API_KEY` model | Single shared key | Per-user JWT tokens |

### Current Setup Flow (Replace)
```bash
# Current (CLI-first)
1. Clone repo
2. Run ./scripts/setup.sh
3. Edit .env or secrets/*.txt files
4. Run python run_bot.py
5. Open dashboard (already configured)
```

### Current Dashboard Assumptions
- Bot is already configured
- Secrets exist in files
- Single user (admin)
- No setup wizard

---

## 3. What Still Needs to Be Built 🚧

### A. User Onboarding Flow (High Priority)

#### Setup Wizard UI
| Step | Feature | Description |
|------|---------|-------------|
| 1 | Welcome | Explain the strategy, risks, requirements |
| 2 | Privy Connect | Create/link Privy app credentials |
| 3 | Wallet Creation | Create EVM + Solana wallets via Privy |
| 4 | Exchange Setup | Connect Asgard API key, Hyperliquid address |
| 5 | Funding | Show wallet addresses, wait for deposits |
| 6 | Strategy Config | Risk limits, position sizing |
| 7 | Review & Launch | Summary, start bot |

#### Backend Endpoints Needed
```python
# New API endpoints
POST /api/setup/privy-config       # Save Privy credentials
POST /api/setup/wallets            # Create wallets via Privy
GET  /api/setup/wallets/status     # Check if wallets funded
POST /api/setup/asgard-config      # Save Asgard API key
POST /api/setup/strategy-config    # Save trading parameters
POST /api/setup/launch             # Start bot
GET  /api/setup/status             # Overall setup status
```

### B. Configuration Management (High Priority)

#### Current: File-Based
```python
# Current - secrets/*.txt files
settings.privy_app_id      # From secrets/privy_app_id.txt
settings.privy_app_secret  # From secrets/privy_app_secret.txt
settings.wallet_address    # From secrets/wallet_address.txt
```

#### New: Database + UI
```python
# New - per-user configuration in SQLite
user_config.privy_app_id       # From UI form -> DB
user_config.evm_wallet_address  # Created via Privy API
user_config.sol_wallet_address  # Created via Privy API
user_config.asgard_api_key      # From UI form -> DB (encrypted)
user_config.strategy_params     # Risk limits, sizing
```

#### Encryption
- Sensitive fields (API keys, Privy secrets) must be encrypted at rest
- Use Fernet (symmetric) or similar
- Key derived from user's password + salt

### C. User Management (Medium Priority)

#### Authentication Flow
```
User visits dashboard
    ↓
Login/Register (if multi-user per deployment)
    ↓
Check setup status (is Privy configured? wallets created? funded?)
    ↓
Redirect to setup wizard OR dashboard
```

#### Database Schema Addition
```sql
-- New tables needed
users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE,
    password_hash TEXT,  -- If doing user auth
    created_at TIMESTAMP
)

user_wallets (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    chain TEXT,  -- 'evm' or 'solana'
    address TEXT,
    privy_wallet_id TEXT,  -- Privy's internal wallet ID
    created_at TIMESTAMP
)

user_config (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    privy_app_id TEXT,
    privy_app_secret_encrypted TEXT,
    privy_auth_key_encrypted TEXT,
    asgard_api_key_encrypted TEXT,
    strategy_config_json TEXT,
    setup_complete BOOLEAN
)
```

### D. Privy Integration Flow (High Priority)

#### Wallet Creation Flow
```python
# New service: services/privy_service.py

async def create_user_wallets(privy_config: PrivyConfig) -> Wallets:
    """Create EVM and Solana wallets for a user."""
    
    client = PrivyClient(
        app_id=privy_config.app_id,
        app_secret=privy_config.app_secret,
        authorization_private_key_path=privy_config.auth_key_path
    )
    
    # Create EVM wallet for Hyperliquid
    evm_wallet = await client.wallet.create(
        chain_type="ethereum",
        # Optional: link to user's existing identity
    )
    
    # Create Solana wallet for Asgard
    sol_wallet = await client.wallet.create(
        chain_type="solana"
    )
    
    return Wallets(
        evm_address=evm_wallet.address,
        sol_address=sol_wallet.address,
        privy_evm_wallet_id=evm_wallet.id,
        privy_sol_wallet_id=sol_wallet.id
    )
```

#### Funding Status Check
```python
# New service: services/funding_service.py

async def check_wallet_funding(wallets: Wallets) -> FundingStatus:
    """Check if wallets have sufficient funds."""
    
    # Check Solana wallet
    sol_client = SolanaClient()
    sol_balance = await sol_client.get_balance(wallets.sol_address)
    sol_usdc = await sol_client.get_token_balance(USDC_MINT, wallets.sol_address)
    
    # Check EVM wallet (Arbitrum)
    arb_client = ArbitrumClient()
    eth_balance = await arb_client.get_balance(wallets.evm_address)
    # Note: USDC on Arbitrum for Hyperliquid
    
    return FundingStatus(
        sol_funded=sol_balance > MIN_SOL,
        sol_usdc_funded=sol_usdc > MIN_USDC,
        arb_funded=eth_balance > MIN_ETH,
        can_trade=all([...])
    )
```

### E. UI/UX Components (Medium Priority)

#### New Pages Needed
| Page | Route | Purpose |
|------|-------|---------|
| Welcome | `/welcome` | Landing page with setup CTA |
| Setup Wizard | `/setup` | Multi-step configuration |
| Wallet Setup | `/setup/wallets` | Create/show wallet addresses |
| Funding | `/setup/funding` | Wait for deposits |
| Strategy Config | `/setup/strategy` | Risk parameters |
| Main Dashboard | `/dashboard` | Current dashboard (modified) |

#### New Components
- `SetupWizard` - Multi-step form
- `PrivyConfigForm` - App ID, Secret, Auth key
- `WalletDisplay` - Show addresses with copy buttons
- `FundingStatus` - Checkmark animation when funded
- `StrategyConfigForm` - Sliders for risk limits

### F. Docker & Deployment (Medium Priority)

#### Current
```yaml
# docker-compose.yml - single user
services:
  bot:
    build: .
    env_file: .env
  
  dashboard:
    build: .
    ports:
      - "8080:8080"
```

#### New Options

**Option 1: Per-User Deployment (Recommended for MVP)**
```yaml
# Each user gets their own docker-compose.yml
# Deployed on their own VPS or managed by you
services:
  bot:
    build: .
    environment:
      - USER_ID=uuid-here
    volumes:
      - ./data/user-uuid:/app/data  # Isolated state
  
  dashboard:
    build: .
    ports:
      - "8080:8080"  # Or unique port per user
```

**Option 2: Multi-Tenant (Future)**
```yaml
# Single deployment, multiple users
services:
  app:
    build: .
    environment:
      - MULTI_TENANT=true
    # Routes by subdomain or path
```

---

## 4. Migration Plan

### Phase 1: Foundation (Week 1-2)
- [ ] Create setup wizard API endpoints
- [ ] Create setup wizard UI pages
- [ ] Implement Privy wallet creation flow
- [ ] Add configuration encryption

### Phase 2: Core Features (Week 3-4)
- [ ] Implement funding status checking
- [ ] Connect setup flow to bot startup
- [ ] Modify dashboard to show setup status
- [ ] Add "reset configuration" feature

### Phase 3: Polish (Week 5-6)
- [ ] Add progress indicators
- [ ] Error handling & validation
- [ ] Email notifications (optional)
- [ ] Documentation

### Phase 4: Deployment (Week 7)
- [ ] Docker image optimization
- [ ] One-click deploy button (Render/Railway)
- [ ] Documentation for self-hosting

---

## 5. Architecture Diagram

### Current Architecture
```
┌─────────────────────────────────────┐
│  User's Computer / VPS              │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │  Bot Core    │  │  Dashboard  │ │
│  │  (Python)    │  │  (FastAPI)  │ │
│  └──────┬───────┘  └──────┬──────┘ │
│         │                 │         │
│  ┌──────▼─────────────────▼──────┐ │
│  │      Secrets (files)          │ │
│  │  - privy_app_id.txt           │ │
│  │  - wallet_address.txt         │ │
│  └───────────────────────────────┘ │
└─────────────────────────────────────┘
```

### New SaaS Architecture
```
┌─────────────────────────────────────────────┐
│  User's VPS / Your Infrastructure           │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │  Web Dashboard (FastAPI + Jinja2)    │  │
│  │                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐ │  │
│  │  │ Setup Wizard │  │  Dashboard   │ │  │
│  │  │  (New)       │  │  (Modified)  │ │  │
│  │  └──────┬───────┘  └──────────────┘ │  │
│  │         │                            │  │
│  │  ┌──────▼──────────────────────┐     │  │
│  │  │   User Config Service       │     │  │
│  │  │  (SQLite + Encryption)      │     │  │
│  │  └──────┬──────────────────────┘     │  │
│  └─────────┼────────────────────────────┘  │
│            │                                │
│  ┌─────────▼──────────────────────┐        │
│  │     Bot Core (DeltaNeutralBot) │        │
│  │                                │        │
│  │  - Uses config from DB         │        │
│  │  - Signs via Privy API         │        │
│  └────────────────────────────────┘        │
└─────────────────────────────────────────────┘
```

---

## 6. Key Technical Decisions

### 1. User Isolation
**Decision:** Single-tenant (one Docker deployment per user)  
**Rationale:** 
- Simpler for MVP
- True isolation (one user's bugs don't affect others)
- Easier to reason about
- Can migrate to multi-tenant later

### 2. Configuration Storage
**Decision:** SQLite with encryption  
**Rationale:**
- No external DB dependency
- Easy to backup
- Works with Docker volumes
- Can migrate to PostgreSQL later

### 3. Privy Model
**Decision:** Users bring your Privy app credentials  
**Rationale:**
- You don't hold their wallet keys
- They control their infrastructure
- Fits self-hosted model

### 4. Frontend Stack
**Decision:** Keep Jinja2 + HTMX/Alpine.js (no React)  
**Rationale:**
- Already built
- Simpler deployment
- Less JS complexity
- Good enough for admin dashboard

---

## 7. File Structure Changes

```
src/
├── dashboard/
│   ├── api/
│   │   ├── control.py          # Existing
│   │   ├── positions.py        # Existing
│   │   ├── status.py           # Existing
│   │   └── setup.py            # NEW: Setup wizard endpoints
│   ├── templates/
│   │   ├── dashboard.html      # Existing
│   │   ├── setup/
│   │   │   ├── welcome.html    # NEW
│   │   │   ├── privy.html      # NEW
│   │   │   ├── wallets.html    # NEW
│   │   │   ├── funding.html    # NEW
│   │   │   └── strategy.html   # NEW
│   │   └── components/
│   │       └── wizard_nav.html # NEW
│   └── services/
│       ├── setup_service.py    # NEW: Setup orchestration
│       ├── privy_service.py    # NEW: Privy API wrapper
│       └── funding_service.py  # NEW: Balance checking
├── core/                       # Existing (unchanged)
└── venues/                     # Existing (unchanged)
```

---

## 8. Risk Assessment

### Technical Risks
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Privy API changes | Medium | High | Abstract behind service layer |
| Wallet creation failures | Low | High | Retry logic + user notification |
| Encryption key loss | Low | Critical | Document key backup procedures |

### Business Risks
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Users don't understand risks | High | High | Clear disclaimers, education |
| Support burden | Medium | Medium | Good documentation, logging |
| Privy pricing changes | Low | Medium | Keep migration path open |

---

## Summary

**Effort Estimate:** 4-6 weeks for MVP  
**Current Readiness:** 70%  
**Biggest Gaps:** Setup wizard, config encryption, user onboarding flow

The foundation is solid. Most work is in the "plumbing" - connecting the existing great trading engine to a smooth web-based onboarding experience.
