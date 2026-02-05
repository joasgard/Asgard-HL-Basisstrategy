# Delta Neutral Funding Rate Arbitrage Bot

**Status:** Phases 1-9 Complete (804 tests passing)  
**Dashboard:** Web UI with real-time monitoring and controls  
**Spec Version:** 2.1

A delta-neutral arbitrage strategy capturing funding rate differentials between **Asgard Finance** (Solana long positions) and **Hyperliquid** (Arbitrum short perpetuals).

---

## 🚀 Quick Start

**New users:** See **[GETTING_STARTED.md](GETTING_STARTED.md)** for complete setup instructions.

```bash
# Quick start for returning users
git clone <repository-url>
cd BasisStrategy
./scripts/setup.sh              # Run setup script
python run_bot.py               # Start the bot
uvicorn src.dashboard.main:app  # Start dashboard (separate terminal)
```

Then open http://localhost:8080 for the web dashboard.

---

## Strategy Overview

```
┌─────────────────────────┐         ┌─────────────────────────┐
│    ASGARD (Solana)      │         │   HYPERLIQUID (Arbitrum)│
│  ┌───────────────────┐  │         │  ┌───────────────────┐  │
│  │  LONG Spot/Margin │  │◄───────►│  │  SHORT Perpetual  │  │
│  │  • 3-4x leverage  │  │  Delta  │  │  • 3-4x leverage  │  │
│  │  • SOL/LST assets │  │ Neutral │  │  • SOL-PERP       │  │
│  │  • Earn funding   │  │         │  │  • Receive funding│  │
│  └───────────────────┘  │         │  └───────────────────┘  │
└─────────────────────────┘         └─────────────────────────┘
```

**Supported Assets:** SOL, jitoSOL, jupSOL, INF

**Yield Sources:**
- Hyperliquid funding payments (shorts paid when funding < 0)
- Asgard lending yield minus borrowing cost
- LST staking rewards (for jitoSOL, jupSOL, INF)

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| **[GETTING_STARTED.md](GETTING_STARTED.md)** | **Step-by-step setup guide for new users** |
| [spec.md](spec.md) | Full technical specification (architecture, formulas, risk limits) |
| [spec-dashboard.md](spec-dashboard.md) | Dashboard technical specification |
| [tracker.md](tracker.md) | Implementation progress and task breakdown |
| [tracker-dashboard.md](tracker-dashboard.md) | Dashboard implementation tracker |
| [SECURITY.md](SECURITY.md) | Security best practices and secret management |
| [test-check.md](test-check.md) | Safety verification test suite |
| [future-releases.md](future-releases.md) | Roadmap and deferred features |

---

## Quick Reference

### Entry Criteria
1. Current funding rate < 0 (shorts paid)
2. Predicted next funding < 0 (shorts will be paid)
3. Total expected APY > 0 after all costs
4. Funding volatility < 50% (1-week lookback)

### Default Parameters
| Parameter | Value |
|-----------|-------|
| Leverage | 3x (max 4x) |
| Min Position | $1,000 |
| Price Deviation Threshold | 0.5% |
| Delta Drift Threshold | 0.5% |

---

## Development Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Project setup, deps, config, logging, retry |
| Phase 2 | ✅ Complete | Core models (enums, funding, opportunity, positions) |
| Phase 2.5 | ✅ Complete | API Security (secrets management) |
| Phase 3 | ✅ Complete | Asgard integration (client, market data, manager) |
| Phase 4 | ✅ Complete | Hyperliquid integration (client, funding, signer, trader) |
| Phase 5.1 | ✅ Complete | Opportunity detector |
| Phase 5.2 | ✅ Complete | Price consensus & fill validator |
| Phase 5.3 | ✅ Complete | Position manager |
| Phase 5.4 | ✅ Complete | Position sizer |
| Phase 5.5 | ✅ Complete | LST correlation monitor |
| Phase 6 | ✅ Complete | Risk engine & circuit breakers |
| Phase 7 | ✅ Complete | Pause controller & emergency stops |
| Phase 8 | ✅ Complete | Shadow trading & paper trading mode |
| Phase 9 | ✅ Complete | **Dashboard** - Web UI with real-time monitoring |

### Completed Work (804 tests passing)
- ✅ **Foundation** - Directory structure, deps, config, logging, retry
- ✅ **Models** - Enums, FundingRate, AsgardRates, ArbitrageOpportunity, Positions
- ✅ **Chain Connection** - Solana/Arbitrum clients, outage detection
- ✅ **Asgard Integration** - Client, market data, state machine, transactions, manager
- ✅ **Hyperliquid Integration** - Client, funding oracle, signer, trader
- ✅ **Core Strategy** - Opportunity detection, price consensus, fill validation
- ✅ **Dashboard** - Web UI, REST API, real-time monitoring, pause/resume controls

See [tracker.md](tracker.md) for detailed task breakdown.

---

## 🖥️ Dashboard

The bot now includes a **web dashboard** for monitoring and control:

| Feature | Description |
|---------|-------------|
| **Real-time Status** | Uptime, positions, PnL, bot status |
| **Position Monitor** | Live position tracking with health metrics |
| **Control Panel** | Pause/resume bot operations |
| **Auto-refresh** | Updates every 5 seconds |
| **Dark Mode** | Default dark theme |

**Access:** http://localhost:8080 (when running)

**Setup:** See [GETTING_STARTED.md](GETTING_STARTED.md#method-2-with-dashboard-recommended)

---

## Usage

### Run Bot Only (Headless)
```bash
source .venv/bin/activate
python run_bot.py
```

### Run Bot + Dashboard
```bash
# Terminal 1 - Bot
source .venv/bin/activate
python run_bot.py

# Terminal 2 - Dashboard
source .venv/bin/activate
uvicorn src.dashboard.main:app --host 0.0.0.0 --port 8080
```

### Run with Docker Compose
```bash
cd docker
docker-compose up -d
```

See [GETTING_STARTED.md](GETTING_STARTED.md) for complete setup details.

---

## Local Development Setup

For detailed setup instructions, see **[GETTING_STARTED.md](GETTING_STARTED.md)**.

Quick summary:
1. Clone repository
2. Run `./scripts/setup.sh`
3. Configure secrets (see GETTING_STARTED.md)
4. Run tests: `pytest tests/ -v`

---

## Safety & Testing

This project includes a comprehensive **804-test** safety suite covering:
- Delta neutrality invariants
- Liquidation protection
- Price consensus validation
- Funding rate safety checks
- Transaction state machine recovery
- Dashboard API security

See [test-check.md](test-check.md) for the safety verification test matrix.

---

*Last updated: 2026-02-05*
