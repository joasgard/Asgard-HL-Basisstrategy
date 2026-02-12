# Asgard Basis

**Status:** Production Ready
**Dashboard:** React SPA with TypeScript, Vite, Tailwind CSS & Privy SDK
**Backend:** FastAPI + PostgreSQL + Redis
**Security:** Privy embedded wallets (no local private keys)

A **market-neutral trading bot** that generates passive income from cryptocurrency funding rates without exposure to price movements.

> **Security Note:** This bot uses [Privy](https://privy.io) for secure wallet infrastructure. Private keys are **never stored locally** - they remain safely sharded in Privy's TEE (Trusted Execution Environment). All signing is done via secure API calls.

---

## How It Makes Money

Cryptocurrency exchanges charge funding rates every 8 hours to balance long/short positions. When many traders are long, longs pay shorts. Our bot captures these payments:

```
+------------------------------------------------------------------+
|                    HOW IT MAKES MONEY                              |
+------------------------------------------------------------------+
|                                                                    |
|  1. BORROW $10,000 on Solana (Asgard)         PAYS ~6% APR       |
|     +-- Buy SOL with borrowed money                               |
|     +-- Earn staking rewards (~3% APR)                             |
|                                                                    |
|  2. SHORT $10,000 on Arbitrum (Hyperliquid)    EARNS ~12% APR     |
|     +-- Sell SOL-PERP to hedge price exposure                      |
|                                                                    |
|  3. RESULT: Price exposure cancels out (DELTA NEUTRAL)             |
|     +-- NET YIELD: ~12% - 6% + 3% = ~9% APR                      |
|                                                                    |
+------------------------------------------------------------------+
```

**Expected Yield: 6-15% APR** (varies with market conditions)

| Investment | Expected Annual | Monthly Average |
|------------|-----------------|-----------------|
| $10,000 | $600 - $1,500 | $50 - $125 |
| $50,000 | $3,000 - $7,500 | $250 - $625 |
| $100,000 | $6,000 - $15,000 | $500 - $1,250 |

### Risk Profile

| Risk | Level | Notes |
|------|-------|-------|
| **Price Risk** | Eliminated | Long and short cancel each other |
| **Funding Risk** | Variable | Rates can turn negative; bot exits automatically |
| **Liquidation Risk** | Low | 3x leverage with automatic margin monitoring |
| **Smart Contract Risk** | Medium | Uses established protocols (Asgard, Hyperliquid) |
| **Custody Risk** | Minimal | Self-custody via Privy embedded wallets |

---

## How It Works

### 1. Opportunity Detection
The bot monitors funding rates continuously. When funding rate < 0 (shorts get paid), predicted rate stays negative, and expected yield > costs, it triggers entry.

### 2. Position Opening
- **Solana (Asgard):** Deposit SOL as collateral, borrow USDC, buy more SOL
- **Arbitrum (Hyperliquid):** Deposit USDC as margin, short SOL-PERP

Result: Long SOL exposure = Short SOL exposure (price neutral)

### 3. Earning Phase
Every 8 hours: receive funding payment on Hyperliquid short, pay borrowing interest on Asgard, earn SOL staking rewards. Net funding accumulates as profit.

### 4. Exit Conditions
Bot closes positions when funding rate turns positive, risk thresholds are breached, or user manually stops.

---

## Quick Start

```bash
# 1. Clone
git clone <repository-url>
cd AsgardBasis

# 2. Setup Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Start PostgreSQL + Redis (Docker recommended)
docker compose -f docker/docker-compose.yml up -d postgres redis

# 4. Configure secrets (7 files)
mkdir -p secrets
echo "your-asgard-api-key" > secrets/asgard_api_key.txt
echo "your-privy-app-id" > secrets/privy_app_id.txt
echo "your-privy-app-secret" > secrets/privy_app_secret.txt
echo "https://solana-rpc.com" > secrets/solana_rpc_url.txt
echo "https://arbitrum-rpc.com" > secrets/arbitrum_rpc_url.txt
openssl rand -hex 32 > secrets/server_secret.txt
openssl ecparam -name prime256v1 -genkey -noout -out secrets/privy_auth.pem

# 5. Build frontend
cd frontend && npm install && npm run build && cd ..

# 6. Start
python run_dashboard.py
```

Open **http://localhost:8080** -> Login with Privy -> Fund wallets -> Trade

See [GETTING_STARTED.md](GETTING_STARTED.md) for complete setup, Docker deployment, and troubleshooting.

---

## Architecture

```
React SPA  ->  FastAPI Backend  ->  PostgreSQL + Redis
                    |
          +---------+---------+
          |                   |
    IntentScanner     PositionMonitor
          |                   |
    UserTradingContext  (per-user exchange clients)
          |                   |
     +---------+    +---------+
     | Asgard  |    | Hyper-  |
     | (Solana)|    | liquid  |
     +---------+    +---------+
```

**Key Design:**
- Multi-user: each user gets Privy-managed wallets + isolated trading context
- Intent-based: users submit entry criteria, bot waits for conditions
- Background monitoring: auto-exit on risk triggers across all users

---

## Project Structure

```
+-- bot/              # Trading engine (core, venues, state)
+-- shared/           # Shared packages (db, models, config, security, chain)
+-- backend/          # FastAPI dashboard (API + React SPA serving)
+-- frontend/         # React SPA (TypeScript, Vite, Tailwind)
+-- migrations/       # PostgreSQL migrations (8 files)
+-- docker/           # Dockerfile + docker-compose.yml
+-- tests/            # Test suite (unit + integration)
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| [GETTING_STARTED.md](GETTING_STARTED.md) | Complete setup, testing & deployment guide |
| [docs/spec.md](docs/spec.md) | Technical specification (v4.0) |
| [docs/tracker.md](docs/tracker.md) | Implementation progress tracker |
| [SECURITY.md](SECURITY.md) | Security practices |

---

## Safety

- 1000+ tests across unit and integration
- Delta neutrality invariants
- Liquidation protection with automatic exit monitoring
- Circuit breakers and risk engine
- Structured error codes with user-friendly messages
- Per-user position isolation

---

## Costs & Fees

- **Hyperliquid**: 0.01% taker fee on trades
- **Asgard**: Variable borrow rate (typically 4-8% APR)
- **Gas Fees**: ~$0.01-0.10 per transaction (Solana + Arbitrum)
- **Minimum**: $5,000+ recommended (gas costs become negligible)

---

*Last updated: 2026-02-12*
