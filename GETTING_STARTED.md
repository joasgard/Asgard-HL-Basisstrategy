# Getting Started

Complete setup guide for Asgard Basis.

---

## Prerequisites

- Python 3.9+
- Node.js 18+
- PostgreSQL 16
- Redis 7
- Git

---

## Quick Setup

### 1. Clone & Install

```bash
git clone <repository-url>
cd AsgardBasis

# Python
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend
npm install
npm run build
cd ..
```

### 2. Start Infrastructure

The easiest way to get PostgreSQL and Redis running:

```bash
# Using Docker (recommended)
docker compose -f docker/docker-compose.yml up -d postgres redis

# Or install natively:
# PostgreSQL: brew install postgresql@16 && brew services start postgresql@16
# Redis: brew install redis && brew services start redis
```

Create the database (if not using Docker):
```bash
createdb basis
```

### 3. Configure Secrets

Create 7 files in `secrets/`:

```bash
mkdir -p secrets

# From external services
echo "your-asgard-key" > secrets/asgard_api_key.txt
echo "your-privy-app-id" > secrets/privy_app_id.txt
echo "your-privy-app-secret" > secrets/privy_app_secret.txt
echo "https://solana-rpc.com" > secrets/solana_rpc_url.txt
echo "https://arbitrum-rpc.com" > secrets/arbitrum_rpc_url.txt

# Generate locally
openssl rand -hex 32 > secrets/server_secret.txt
openssl ecparam -name prime256v1 -genkey -noout -out secrets/privy_auth.pem

# Secure permissions
chmod 600 secrets/*
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your database URL and other settings
```

Key variables:
```bash
DATABASE_URL=postgresql://basis:basis@localhost:5432/basis
REDIS_URL=redis://localhost:6379
VITE_PRIVY_APP_ID=your-privy-app-id
```

### 5. Register Privy Key

```bash
# Generate public key for Privy dashboard
openssl ec -in secrets/privy_auth.pem -pubout -out secrets/privy_auth.pub.pem
cat secrets/privy_auth.pub.pem
# Copy this to https://dashboard.privy.io -> Settings -> Auth Keys
```

### 6. Start

```bash
source .venv/bin/activate
python run_dashboard.py
```

Open **http://localhost:8080** -> Login -> Fund wallets -> Trade

---

## Detailed Setup

### 1. Get API Keys

| Service | What You Need | URL |
|---------|---------------|-----|
| Asgard | API Key | asgard.finance |
| Privy | App ID + App Secret | dashboard.privy.io |
| Helius | Solana RPC URL | helius.dev |
| Alchemy | Arbitrum RPC URL | alchemy.com |

### 2. Privy Setup

1. Sign up at [privy.io](https://privy.io)
2. Create app -> Copy App ID and App Secret
3. Enable Email login method
4. Enable embedded wallets for Ethereum + Solana
5. Go to Settings -> Auth Keys
6. Copy contents of `privy_auth.pub.pem` and save

### 3. Fund Wallets

After first login, the dashboard creates:

- **Solana wallet** - Send SOL for gas + collateral
- **Arbitrum wallet** - Send USDC for Hyperliquid margin

Click "Deposit" button in dashboard to see addresses.

---

## Local Testing Checklist

### Test 1: Infrastructure Running

```bash
# PostgreSQL
psql postgresql://basis:basis@localhost:5432/basis -c "SELECT 1"

# Redis
redis-cli ping
# Should return: PONG
```

### Test 2: Frontend Build

```bash
cd frontend
npm run build
# Should complete without errors
ls -la dist/
```

### Test 3: Backend Starts

```bash
source .venv/bin/activate
python run_dashboard.py

# Should see:
# - "Connecting to PostgreSQL..."
# - "Database schema version: 8"
# - "Redis connected"
# - "Position monitor service started"
# - "Intent scanner service started"
# - "Dashboard API ready"
```

### Test 4: API Health Check

```bash
# In another terminal
curl http://localhost:8080/health/ready

# Should return:
# {"status":"ready","database":"healthy","redis":"healthy",...}
```

### Test 5: Frontend Loads

```bash
open http://localhost:8080

# Should see:
# - React SPA with "Asgard Basis" branding
# - "Connect" button (Privy login)
```

### Test 6: Authentication

1. Click **"Connect"**
2. Login with email (Privy modal)
3. Enter OTP from email
4. Should see dashboard with wallet addresses

### Test 7: API Endpoints

```bash
curl http://localhost:8080/api/v1/rates
curl http://localhost:8080/api/v1/health/ready
```

---

## Docker Deployment

### Development

```bash
cd docker
docker compose up -d
# Starts: PostgreSQL + Redis + Bot
# Access at http://localhost:8080
```

### Production

```bash
# Configure .env with production values first
docker compose -f docker-compose.prod.yml up -d
# Starts: PostgreSQL + Redis + App + Nginx
# Access at https://yourdomain.com (port 80/443)
```

### Production Checklist

- [ ] 7 secrets files configured
- [ ] `chmod 600 secrets/*`
- [ ] Privy auth key registered in dashboard
- [ ] Frontend built: `cd frontend && npm run build`
- [ ] `.env` configured with production DATABASE_URL and POSTGRES_PASSWORD
- [ ] Nginx TLS certificates in place
- [ ] Firewall: only ports 80/443 open
- [ ] Test with small position first

---

## Testing

```bash
source .venv/bin/activate

# All tests
pytest tests/ -v

# Specific module
pytest tests/unit/core/ -v
pytest tests/unit/dashboard/ -v
pytest tests/unit/venues/ -v

# With coverage
pytest --cov=. --cov-report=html
# View at htmlcov/index.html

# Frontend tests
cd frontend && npm test
```

---

## Troubleshooting

### Dashboard won't start

```bash
# Check PostgreSQL is running
psql postgresql://basis:basis@localhost:5432/basis -c "SELECT 1"

# Check Redis is running
redis-cli ping

# Check secrets exist
ls secrets/*.txt secrets/*.pem | wc -l  # Should be 7

# Verify imports
python -c "from backend.dashboard.main import create_app; print('OK')"
```

### Database errors

```bash
# Check connection
psql postgresql://basis:basis@localhost:5432/basis

# Reset database (WARNING: loses all data)
dropdb basis && createdb basis
python run_dashboard.py  # Migrations will run automatically
```

### Port already in use

```bash
# Kill process on port 8080
lsof -ti:8080 | xargs kill -9

# Or use different port
uvicorn backend.dashboard.main:app --port 8081
```

### Frontend not showing

```bash
# Make sure frontend is built
cd frontend && npm run build

# Check dist/ exists
ls frontend/dist/index.html
```

---

## Project Structure

```
AsgardBasis/
+-- bot/              # Trading engine (core logic, venues, state)
+-- shared/           # Shared packages (db, models, config, security)
+-- backend/          # FastAPI dashboard (API + SPA serving)
+-- frontend/         # React SPA (TypeScript, Vite, Tailwind)
+-- migrations/       # PostgreSQL schema migrations
+-- docker/           # Docker configuration
+-- tests/            # Test suite (unit + integration)
+-- secrets/          # API keys (git-ignored)
+-- run_dashboard.py  # Local development entry point
```

---

## Next Steps

1. Read the [README](README.md) for strategy overview
2. Read [docs/spec.md](docs/spec.md) for technical details
3. Review [SECURITY.md](SECURITY.md) for security practices
4. Start with small positions to test

---

*Last updated: 2026-02-12*
