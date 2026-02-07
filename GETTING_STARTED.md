# Getting Started Guide

A step-by-step guide to set up and run the Delta Neutral Funding Rate Arbitrage Bot.

---

## 📋 Prerequisites

- **Python 3.9+**
- **Git**
- **Docker & Docker Compose** (optional, for containerized deployment)
- **Privy Account** (free) from [privy.io](https://privy.io) - for secure wallet infrastructure

> **Note:** Exchange API keys are **optional**. Both Asgard and Hyperliquid work with wallet-based authentication.

---

## 🚀 Quick Start (3 minutes)

### 1. Clone the Repository

```bash
git clone <repository-url>
cd BasisStrategy
```

### 2. Run Setup Script

```bash
./scripts/setup.sh
```

This will:
- Check Python version
- Create virtual environment (`.venv`)
- Install dependencies
- Create required directories
- Set up secret files

### 3. Start the Dashboard

```bash
source .venv/bin/activate
uvicorn src.dashboard.main:app --host 0.0.0.0 --port 8080
```

Then open **http://localhost:8080** and follow the 3-step setup wizard:

| Step | Action | Description |
|------|--------|-------------|
| 1 | **Login** | Sign in with Privy (Google, Twitter, etc.) |
| 2 | **Wallets** | Create Solana + Arbitrum wallets |
| 3 | **Exchange** | Optional: Add API keys for higher rate limits |

That's it! You're ready to trade.

---

## 📖 Detailed Setup

### Privy Configuration (Required)

The bot uses **Privy** for secure, server-side wallet management.

#### 1. Create Privy App

1. Go to [https://dashboard.privy.io](https://dashboard.privy.io) and sign up
2. Create a new app
3. Copy your **App ID** and **App Secret**

#### 2. Configure Server Secret

```bash
# Generate a secure server secret for encryption
openssl rand -hex 32 > secrets/server_secret.txt

# Add your Privy credentials
echo "your_privy_app_id" > secrets/privy_app_id.txt
echo "your_privy_app_secret" > secrets/privy_app_secret.txt
```

#### 3. Set Secure Permissions

```bash
chmod 600 secrets/*.txt
```

---

## 🌐 Using the Dashboard

### First Time Setup Wizard

The dashboard includes a guided 3-step setup:

#### Step 1: Authentication
- Click "Sign in with Privy"
- Login with Google, Twitter, or email
- Your user ID becomes your account identifier

#### Step 2: Wallet Setup
- The dashboard creates two wallets via Privy:
  - **Solana wallet** - For Asgard trading
  - **Arbitrum wallet** - For Hyperliquid trading
- Fund these wallets with USDC to start trading

#### Step 3: Exchange Configuration (Optional)
- **Asgard**: Public access (1 req/sec) or add API key for unlimited
- **Hyperliquid**: Wallet-based auth (no key needed)
- Click "Skip" to use wallet-based authentication

### Main Dashboard Features

After setup, the dashboard shows:

| Feature | Description |
|---------|-------------|
| **🔴 Fund Wallets** | Deposit USDC to your trading wallets |
| **🟢 Launch Strategy** | Start the arbitrage bot |
| **Status Cards** | Bot status, positions count, PnL |
| **Positions List** | Real-time position monitoring |
| **Control Panel** | Pause/resume trading |

---

## 💰 Funding Your Wallets

Before trading, fund your wallets:

### Solana Wallet (Asgard)
- Send **SOL** - For transaction fees
- Send **USDC** - For margin trading

### Arbitrum Wallet (Hyperliquid)
- Send **ETH** - For transaction fees (small amount)
- Send **USDC** - For perpetual trading

Use the "🔴 Fund Wallets" button on the dashboard to see your wallet addresses.

---

## 🔧 Optional: API Keys for Higher Rate Limits

Both exchanges work without API keys, but you can add them for higher rate limits:

### Asgard API Key (Optional)

```bash
# Contact Asgard for an API key
echo "your_asgard_api_key" > secrets/asgard_api_key.txt
```

| Access Type | Rate Limit |
|-------------|------------|
| No API Key | 1 req/sec (IP-based) |
| With API Key | Unlimited |

### Hyperliquid API Key (Optional)

Hyperliquid uses your EVM wallet for authentication (EIP-712 signatures). API keys are only needed for higher rate limits.

---

## 🏃 Running the Bot

### Method 1: Dashboard-First (Recommended)

```bash
source .venv/bin/activate
uvicorn src.dashboard.main:app --port 8080
```

Open http://localhost:8080, complete the 3-step wizard, then click **"🟢 Launch Strategy"**.

### Method 2: Headless Bot

```bash
source .venv/bin/activate
python run_bot.py
```

### Method 3: Docker Compose (Production)

```bash
cd docker

# Create environment file
cp ../.env.example .env
# Edit .env with your credentials

# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

Access dashboard at http://localhost:8080

---

## 🔒 Security

### How It Works

1. **Privy manages wallets** - Private keys never touch your server
2. **Server-side signing** - Transactions signed via Privy's secure API
3. **Field-level encryption** - API keys encrypted at rest using AES-256-GCM
4. **No local keys** - Unlike traditional setups, no `*_private_key.txt` files exist

### Security Checklist

Before running with real funds:

- [ ] Created Privy account and configured credentials
- [ ] Generated secure `server_secret.txt` for encryption
- [ ] Set restrictive permissions: `chmod 600 secrets/*`
- [ ] Verified `.env` and `secrets/` are in `.gitignore`
- [ ] Tested with small amounts first
- [ ] Verified dashboard is not exposed to public internet

---

## 🧪 Testing Your Setup

### Run Tests

```bash
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# Run bot tests only
pytest tests/unit/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Verify Configuration

```bash
# Test imports
python -c "from src.config.settings import get_settings; print('✓ Settings OK')"
python -c "from src.core.bot import DeltaNeutralBot; print('✓ Bot OK')"
python -c "from src.dashboard.main import app; print('✓ Dashboard OK')"

# Test Privy connection
python -c "
from src.venues.privy_client import get_privy_client
client = get_privy_client()
print('✓ Privy client initialized')
"
```

---

## 🐛 Troubleshooting

### Dashboard won't start

```bash
# Check Python version
python3 --version  # Should be 3.9+

# Verify virtual environment
source .venv/bin/activate
which python  # Should show .venv path

# Check dependencies
pip list | grep -E "(fastapi|privy|web3)"
```

### Privy authentication errors

```bash
# Verify credentials are set
cat secrets/privy_app_id.txt
cat secrets/privy_app_secret.txt

# Test Privy connection
python -c "
from src.venues.privy_client import get_privy_client
client = get_privy_client()
print('✓ Privy client initialized')
"
```

### Missing exchange data

```bash
# Check if public API access is working
curl https://v2-ultra-edge.asgard.finance/margin-trading/markets

# Test with optional API key if you have one
curl -H "X-API-Key: your_key" https://v2-ultra-edge.asgard.finance/margin-trading/markets
```

### Docker issues

```bash
# Rebuild containers
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Check logs
docker-compose logs bot
docker-compose logs dashboard
```

---

## 📚 Next Steps

1. **Read the spec**: See [docs/specs/spec.md](docs/specs/spec.md) for full technical details
2. **Review architecture**: Check architecture docs in `docs/architecture/`
3. **Monitor performance**: Use the dashboard to track PnL and positions
4. **Add API keys later**: Contact exchanges if you need higher rate limits

---

## 💡 Tips

- **Start small**: Test with minimum position sizes first
- **Fund both wallets**: You need USDC on both Solana and Arbitrum
- **Monitor funding rates**: Dashboard shows real-time funding PnL
- **Use pause**: Pause entry during volatile markets
- **Check health**: Use `/health` endpoint for monitoring
- **No API keys needed**: Both exchanges work with wallet-based auth

---

**Need help?** Check [SECURITY.md](SECURITY.md) for security best practices and [README.md](README.md) for project overview.
