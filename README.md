# Delta Neutral Funding Rate Arbitrage Bot

**Status:** Phases 1-9 Complete (686 tests passing)  
**Spec Version:** 2.1

A delta-neutral arbitrage strategy capturing funding rate differentials between **Asgard Finance** (Solana long positions) and **Hyperliquid** (Arbitrum short perpetuals).

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

## Documentation

| Document | Purpose |
|----------|---------|
| [spec.md](spec.md) | Full technical specification (architecture, formulas, risk limits) |
| [tracker.md](tracker.md) | Implementation progress, task breakdown, and status |
| [test-check.md](test-check.md) | 170-test safety verification suite |
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

### Completed Work (686 tests passing)
- ✅ **Foundation** - Directory structure, deps, config, logging, retry
- ✅ **Models** - Enums, FundingRate, AsgardRates, ArbitrageOpportunity, Positions
- ✅ **Chain Connection** - Solana/Arbitrum clients, outage detection
- ✅ **Asgard Integration** - Client, market data, state machine, transactions, manager
- ✅ **Hyperliquid Integration** - Client, funding oracle, signer, trader
- ✅ **Core Strategy** - Opportunity detection, price consensus, fill validation

See [tracker.md](tracker.md) for detailed task breakdown.

---

## Local Development Setup

### Prerequisites
- Python 3.9+
- Git

### 1. Clone the Repository

```bash
git clone <repository-url>
cd BasisStrategy
```

### 2. Create Virtual Environment

```bash
# Create venv
python3 -m venv .venv

# Activate venv
# macOS/Linux:
source .venv/bin/activate

# Windows:
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Make sure venv is activated (you should see (.venv) in your prompt)
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your API keys and configuration
# Required variables:
# - ASGARD_API_KEY
# - SOLANA_RPC_URL (recommend Helius or Triton)
# - SOLANA_PRIVATE_KEY
# - HYPERLIQUID_WALLET_ADDRESS
# - HYPERLIQUID_PRIVATE_KEY
```

**Security Note:** Never commit `.env` to git. It's already in `.gitignore`.

### 5. Run Tests

```bash
# Ensure venv is activated
source .venv/bin/activate

# Run all unit tests
pytest tests/unit/ -v

# Run with coverage report
pytest tests/unit/ --cov=src --cov-report=html
```

### 6. Verify Setup

```bash
# Test imports work
python -c "from src.config.settings import get_settings; print('✓ Settings OK')"
python -c "from src.models.common import Asset; print('✓ Models OK')"
python -c "from src.chain.solana import SolanaClient; print('✓ Chain clients OK')"
```

---

## Usage

### Paper Trading Mode (Future)

```bash
source .venv/bin/activate
python -m src.main --paper
```

### Live Trading (Future)

```bash
source .venv/bin/activate
python -m src.main
```

---

## Safety & Testing

This project includes a comprehensive 299-test safety suite covering:
- Delta neutrality invariants
- Liquidation protection
- Price consensus validation
- Funding rate safety checks
- Transaction state machine recovery

See [test-check.md](test-check.md) for the safety verification test matrix.

---

*Last updated: 2026-02-05*
