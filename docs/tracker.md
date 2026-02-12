# Asgard Basis - Implementation Tracker

**Project:** Asgard Basis
**Spec:** [docs/spec.md](./spec.md) (v4.0 - Multi-User SaaS)
**Quick Start:** [GETTING_STARTED.md](../GETTING_STARTED.md)
**Security:** [SECURITY.md](../SECURITY.md)
**Strategy:** Equal Leverage Delta Neutral (1.1-4x, default 3x)
**Deployment:** PostgreSQL + Redis + FastAPI + React SPA (Docker)
**Auth:** Privy Email + OTP with Embedded Wallets
**UX:** Connect -> Email -> OTP -> Auto Wallets -> Dashboard

---

## Status Legend

- `[x]` **BUILT** - Fully implemented and tested
- `[~]` **PARTIAL** - Started but incomplete
- `[ ]` **NOT BUILT** - Not started

---

## CORE ENGINE ✅

The core trading engine is **COMPLETE** with 1000+ tests passing. Built in Phases 1-8 (pre-SaaS).

### Phase 1: Project Setup

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Project structure | `bot/`, `shared/`, `backend/` | `[x]` | 17 passing |
| Dependencies | `requirements/base.txt`, `requirements/bot.txt` | `[x]` | - |
| Configuration | `shared/config/settings.py` | `[x]` | - |
| Assets & risk params | `shared/config/assets.py`, `shared/config/risk.yaml` | `[x]` | - |
| Logging | `shared/utils/logger.py` | `[x]` | - |
| Retry utilities | `shared/utils/retry.py` | `[x]` | - |

### Phase 2: Core Models

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Enums (Protocol, Chain) | `shared/models/common.py` | `[x]` | 48 passing |
| Funding models | `shared/models/funding.py` | `[x]` | - |
| Opportunity model | `shared/models/opportunity.py` | `[x]` | - |
| Position models | `shared/models/position.py` | `[x]` | - |
| Chain clients (Solana/Arbitrum) | `shared/chain/` | `[x]` | - |
| Outage detector | `shared/chain/outage_detector.py` | `[x]` | - |

### Phase 3: Asgard Integration

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Asgard API client | `bot/venues/asgard/client.py` | `[x]` | 58 passing |
| Market data & rates | `bot/venues/asgard/market_data.py` | `[x]` | - |
| Transaction state machine | `bot/state/state_machine.py` | `[x]` | - |
| Transaction builder | `bot/venues/asgard/transactions.py` | `[x]` | - |
| Position manager | `bot/venues/asgard/manager.py` | `[x]` | - |

### Phase 4: Hyperliquid Integration

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Hyperliquid API client | `bot/venues/hyperliquid/client.py` | `[x]` | 72 passing |
| Funding oracle | `bot/venues/hyperliquid/funding_oracle.py` | `[x]` | - |
| EIP-712 signer | `bot/venues/hyperliquid/signer.py` | `[x]` | - |
| Trading with retry | `bot/venues/hyperliquid/trader.py` | `[x]` | - |
| USDC depositor | `bot/venues/hyperliquid/depositor.py` | `[x]` | - |

### Phase 5: Core Strategy

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Opportunity detector | `bot/core/opportunity_detector.py` | `[x]` | 111 passing |
| Price consensus | `bot/core/price_consensus.py` | `[x]` | - |
| Fill validator | `bot/core/fill_validator.py` | `[x]` | - |
| Position manager | `bot/core/position_manager.py` | `[x]` | - |
| Position sizer | `bot/core/position_sizer.py` | `[x]` | - |
| LST correlation monitor | `bot/core/lst_monitor.py` | `[x]` | - |

### Phase 6: Risk Management

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Risk engine | `bot/core/risk_engine.py` | `[x]` | 153 passing |
| Pause controller | `bot/core/pause_controller.py` | `[x]` | - |
| Circuit breakers | `bot/core/risk_engine.py` | `[x]` | - |
| Transaction validator | `shared/security/transaction_validator.py` | `[x]` | - |

### Phase 7: Main Bot Loop

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Bot runner | `bot/core/bot.py` | `[x]` | 45 passing |
| State persistence | `bot/state/persistence.py` | `[x]` | - |
| Recovery on startup | `bot/state/persistence.py` | `[x]` | - |

### Phase 8: Testing & Deployment

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| Integration tests | `tests/integration/` | `[x]` | 133 passing |
| Docker setup | `docker/` | `[x]` | - |

---

## INFRASTRUCTURE ✅

### Database (PostgreSQL)

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| PostgreSQL async client | `shared/db/database.py` | `[x]` | asyncpg, connection pooling |
| Migration system | `shared/db/migrations.py` | `[x]` | Checksum-based versioning |
| 8 migration files | `migrations/001-008` | `[x]` | Initial -> job durability |
| User-scoped positions | `migrations/005` | `[x]` | JSONB position data |
| Intent table | `migrations/007` | `[x]` | Full intent lifecycle |
| Job durability | `migrations/008` | `[x]` | retry_count, last_error |

### Redis

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| Connection pooling | `shared/redis_client.py` | `[x]` | Singleton aioredis pool |
| Rate limiting | `backend/dashboard/middleware/rate_limit.py` | `[x]` | Per-IP + per-user |
| SSE pub/sub | `backend/dashboard/events_manager.py` | `[x]` | Multi-instance support |
| Distributed locks | `backend/dashboard/main.py` | `[x]` | Service lock helpers |

### Docker

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| Multi-stage Dockerfile | `docker/Dockerfile` | `[x]` | Frontend build + Python |
| Dev compose | `docker/docker-compose.yml` | `[x]` | PG + Redis + Bot |
| Prod compose | `docker-compose.prod.yml` | `[x]` | + Nginx reverse proxy |
| Non-root user | `docker/Dockerfile` | `[x]` | UID 1000 |
| Read-only filesystem | `docker/docker-compose.yml` | `[x]` | tmpfs for writable dirs |
| Health checks | All compose files | `[x]` | All services |

---

## SAAS FEATURES ✅

### Authentication

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| Privy React SDK | `frontend/src/App.tsx` | `[x]` | Email + OTP login |
| Auth sync endpoint | `backend/dashboard/api/auth.py` | `[x]` | POST /auth/sync |
| Users table | `migrations/004_users_table.sql` | `[x]` | Privy ID, email, wallets |
| Wallet creation | `backend/dashboard/privy_client.py` | `[x]` | Auto Solana + EVM |
| Ensure wallets flow | `backend/dashboard/api/wallet_setup.py` | `[x]` | Handles race conditions |
| Session management | `backend/dashboard/auth.py` | `[x]` | JWT httpOnly cookies |

### Dashboard (React SPA)

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| React + Vite + TS | `frontend/` | `[x]` | Tailwind CSS |
| Dashboard view | `frontend/src/components/dashboard/` | `[x]` | Rates + positions |
| Positions view | `frontend/src/components/positions/` | `[x]` | Cards + modals |
| Settings view | `frontend/src/components/settings/` | `[x]` | Strategy config |
| Open position modal | `frontend/src/components/positions/OpenPositionModal.tsx` | `[x]` | Balance validation |
| Close position modal | `frontend/src/components/positions/ClosePositionModal.tsx` | `[x]` | Async job tracking |
| Error boundary | `frontend/src/components/ErrorBoundary.tsx` | `[x]` | Graceful errors |
| SSE hook | `frontend/src/hooks/` | `[x]` | Real-time updates |
| API client | `frontend/src/api/client.ts` | `[x]` | Typed API calls |
| SPA serving | `backend/dashboard/main.py` | `[x]` | Fallback to index.html |

### Backend API

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| FastAPI app factory | `backend/dashboard/main.py` | `[x]` | Lifespan management |
| Auth API | `backend/dashboard/api/auth.py` | `[x]` | sync, logout, me |
| Positions API | `backend/dashboard/api/positions.py` | `[x]` | CRUD + async jobs |
| Intents API | `backend/dashboard/api/intents.py` | `[x]` | CRUD + balance preflight |
| Balances API | `backend/dashboard/api/balances.py` | `[x]` | Per-user on-chain balances |
| Rates API | `backend/dashboard/api/rates.py` | `[x]` | Asgard + HL rates |
| Settings API | `backend/dashboard/api/settings.py` | `[x]` | Load/save/reset |
| Control API | `backend/dashboard/api/control.py` | `[x]` | Pause/resume |
| Events API (SSE) | `backend/dashboard/api/events.py` | `[x]` | Real-time stream |
| Health endpoints | `backend/dashboard/main.py` | `[x]` | Live + ready probes |
| Bot bridge | `backend/dashboard/bot_bridge.py` | `[x]` | Cached HTTP bridge |
| Middleware stack | `backend/dashboard/main.py` | `[x]` | Request ID, logging, security, rate limit, CORS |

### Multi-User Execution

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| Per-user signer | `bot/venues/hyperliquid/signer.py` | `[x]` | Accepts user wallet context |
| Per-user trader | `bot/venues/hyperliquid/trader.py` | `[x]` | Instance-scoped wallet |
| Per-user Asgard | `bot/venues/asgard/manager.py` | `[x]` | User wallet passthrough |
| UserTradingContext | `bot/venues/user_context.py` | `[x]` | Factory for per-user clients |
| Position scoping | `migrations/005` | `[x]` | user_id on all positions |

### Background Services

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| PositionMonitorService | `bot/core/position_monitor.py` | `[x]` | 30s cycle, multi-tenant |
| IntentScanner | `bot/core/intent_scanner.py` | `[x]` | 60s cycle, criteria checks |
| Job recovery | `backend/dashboard/main.py` | `[x]` | Mark stuck jobs on startup |
| Distributed locks | `backend/dashboard/main.py` | `[x]` | Redis-based service locks |

### Error Handling

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| Error codes | `bot/core/errors/codes.py` | `[x]` | 9 categories, 30+ codes |
| Exception types | `bot/core/errors/exceptions.py` | `[x]` | Typed exceptions |
| Error handlers | `bot/core/errors/handlers.py` | `[x]` | FastAPI integration |
| Error migration | `migrations/006` | `[x]` | error_code on jobs |

### Emergency Stop

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| API pause/resume | `backend/dashboard/api/control.py` | `[x]` | Pauses bot operations |
| File-based kill switch | `bot/core/kill_switch.py` | `[x]` | Filesystem trigger |
| Manual position close | `backend/dashboard/api/positions.py` | `[x]` | Works when bot paused |
| Docker stop handler | `bot/core/bot.py` | `[x]` | SIGTERM/SIGINT |

---

## METRICS

| Metric | Value |
|--------|-------|
| Tests Passing | 1000+ |
| Test Coverage | ~85% |
| Python Files | ~90 (bot: 35, shared: 26, backend: 29) |
| Migrations | 8 |
| API Endpoints | ~25 |
| Error Code Categories | 9 |
| Supported Assets | SOL, jitoSOL, jupSOL, INF |
| Supported Venues | 2 (Asgard, Hyperliquid) |
| Leverage Range | 1.1x - 4x |
| Background Services | 2 (PositionMonitor, IntentScanner) |

---

## REMAINING WORK

### Frontend Polish
- [ ] Intent UI (IntentCard, pending intents list, cancel button)
- [ ] Refactor `POST /positions/open` to create intent by default (with `execute_immediately` override)

### Future Enhancements
- [ ] Paper trading / shadow mode
- [ ] Telegram alert integration
- [ ] Advanced exit logic (patience mode)
- [ ] Multi-venue support (beyond Asgard/Hyperliquid)
- [ ] Billing / usage tracking for hosted SaaS

---

## REFERENCE

### Quick Commands

```bash
# Run tests
source .venv/bin/activate
pytest tests/ -v

# Run dashboard (local dev)
python run_dashboard.py

# Run with Docker (production)
docker compose -f docker-compose.prod.yml up -d

# Build frontend
cd frontend && npm install && npm run build
```

### Environment Variables

```bash
# Required
DATABASE_URL=postgresql://basis:basis@localhost:5432/basis
REDIS_URL=redis://localhost:6379

# Secrets (loaded from secrets/ directory)
# server_secret.txt, privy_app_id.txt, privy_app_secret.txt
# privy_auth.pem, solana_rpc_url.txt, arbitrum_rpc_url.txt
# asgard_api_key.txt

# Optional
DASHBOARD_ENV=development
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:5173
```

---

## CHANGE LOG

### v10.1 (2026-02-12)
- **Documentation refresh**: Updated all paths to match actual codebase
- Reflects modular architecture: `bot/` + `shared/` + `backend/`
- PostgreSQL + Redis infrastructure documented
- All 4 SaaS sprints marked complete
- Error code system documented
- Background services (IntentScanner, PositionMonitor) documented

### v10.0 (2026-02-11)
- All 4 SaaS sprints complete
- Sprint 1: Per-user signer resolution
- Sprint 2: Position monitoring service
- Sprint 3: Intent-based position entry
- Sprint 4: Balance gating

---

*Last Updated: 2026-02-12*
*Tracker Version: 10.1*
*Spec Reference: docs/spec.md v4.0*
