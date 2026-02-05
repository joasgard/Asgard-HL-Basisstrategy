# Getting Started Guide

A step-by-step guide to set up and run the Delta Neutral Funding Rate Arbitrage Bot.

---

## 📋 Prerequisites

- **Python 3.9+**
- **Git**
- **Docker & Docker Compose** (optional, for containerized deployment)
- **API Keys** from:
  - [Asgard Finance](https://asgard.finance)
  - [Helius](https://helius.xyz) or other Solana RPC provider
  - Self-generated Solana wallet
  - Self-generated Hyperliquid wallet (secp256k1)

---

## 🚀 Quick Start (5 minutes)

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

### 3. Configure Secrets

Choose **one** of these methods:

#### Option A: Secrets Directory (Recommended)

```bash
# Copy example files
cp secrets/asgard_api_key.txt.example secrets/asgard_api_key.txt
cp secrets/solana_private_key.txt.example secrets/solana_private_key.txt
cp secrets/hyperliquid_private_key.txt.example secrets/hyperliquid_private_key.txt
cp secrets/hyperliquid_wallet_address.txt.example secrets/hyperliquid_wallet_address.txt
cp secrets/admin_api_key.txt.example secrets/admin_api_key.txt

# Edit with your actual credentials
echo "your_asgard_api_key" > secrets/asgard_api_key.txt
echo "your_solana_private_key" > secrets/solana_private_key.txt
echo "your_hyperliquid_private_key" > secrets/hyperliquid_private_key.txt
echo "your_hyperliquid_wallet_address" > secrets/hyperliquid_wallet_address.txt

# Generate a secure admin key for dashboard access
openssl rand -hex 32 > secrets/admin_api_key.txt

# Set secure permissions
chmod 600 secrets/*.txt
```

#### Option B: Environment Variables

```bash
# Add to your shell profile (~/.bashrc, ~/.zshrc, etc.)
export ASGARD_API_KEY="your_asgard_api_key"
export SOLANA_RPC_URL="https://your-rpc-url.com"
export SOLANA_PRIVATE_KEY="your_solana_private_key"
export HYPERLIQUID_WALLET_ADDRESS="your_hyperliquid_wallet_address"
export HYPERLIQUID_PRIVATE_KEY="your_hyperliquid_private_key"
export ADMIN_API_KEY="your_secure_random_key"
```

#### Option C: .env File (Development Only)

```bash
# Copy example file
cp .env.example .env

# Edit .env with your credentials
nano .env  # or use your preferred editor
```

---

## 🏃 Running the Bot

### Method 1: Local Python (Development)

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the bot
python run_bot.py
```

The bot will:
1. Connect to Solana and Arbitrum
2. Start monitoring for opportunities
3. Open positions when criteria are met
4. Run until you press Ctrl+C

### Method 2: With Dashboard (Recommended)

**Terminal 1 - Bot:**
```bash
source .venv/bin/activate
python run_bot.py
```

**Terminal 2 - Dashboard:**
```bash
source .venv/bin/activate
uvicorn src.dashboard.main:app --host 0.0.0.0 --port 8080
```

Then open http://localhost:8080 in your browser.

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

## 🌐 Using the Dashboard

### First Time Setup

1. Open http://localhost:8080
2. Enter your `ADMIN_API_KEY` when prompted (for pause/resume controls)
3. The API key is saved in browser localStorage for convenience

### Dashboard Features

| Feature | Description |
|---------|-------------|
| **Status Cards** | Uptime, positions count, total PnL, bot status |
| **Control Panel** | Pause Entry, Pause All, Resume buttons |
| **Positions List** | Real-time position monitoring with PnL |
| **Auto-Refresh** | Updates every 5 seconds automatically |

### API Endpoints

The dashboard also provides a REST API:

```bash
# Health check
curl http://localhost:8080/health

# Get status (requires auth)
curl -H "Authorization: Bearer $ADMIN_API_KEY" http://localhost:8080/api/v1/status

# List positions
curl -H "Authorization: Bearer $ADMIN_API_KEY" http://localhost:8080/api/v1/positions

# Pause bot
curl -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -d '{"reason": "Maintenance", "scope": "all", "api_key": "'$ADMIN_API_KEY'"}' \
  http://localhost:8080/api/v1/control/pause
```

---

## 🔧 Configuration Options

### Bot Configuration

Edit `run_bot.py` to customize:

```python
config = BotConfig(
    max_concurrent_positions=5,      # Max open positions
    min_opportunity_apy=0.01,        # 1% minimum APY
    enable_auto_exit=True,           # Auto-close on triggers
    enable_circuit_breakers=True,    # Safety circuit breakers
    admin_api_key=settings.admin_api_key,
)
```

### Dashboard Configuration

Set via environment variables:

```bash
export DASHBOARD_HOST=0.0.0.0      # Bind address
export DASHBOARD_PORT=8080         # Port
export BOT_API_URL=http://bot:8000 # Bot internal API
export CACHE_TTL=5.0               # Cache duration (seconds)
```

---

## 🧪 Testing Your Setup

### Run Tests

```bash
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# Run bot tests only
pytest tests/unit/ -v

# Run dashboard tests only
pytest tests/dashboard/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Verify Configuration

```bash
# Test imports
python -c "from src.config.settings import get_settings; print('✓ Settings OK')"
python -c "from src.core.bot import DeltaNeutralBot; print('✓ Bot OK')"
python -c "from src.dashboard.main import app; print('✓ Dashboard OK')"

# Test configuration loading
python -c "
from src.config.settings import get_settings
settings = get_settings()
print(f'✓ Config loaded: {settings}')
"
```

---

## 🔒 Security Checklist

Before running with real funds:

- [ ] Created separate wallets for dev/prod
- [ ] Set restrictive permissions on secrets: `chmod 600 secrets/*`
- [ ] Verified `.env` and `secrets/` are in `.gitignore`
- [ ] Generated strong `ADMIN_API_KEY`
- [ ] Tested with small amounts first
- [ ] Verified dashboard is not exposed to public internet

---

## 🐛 Troubleshooting

### Bot won't start

```bash
# Check Python version
python3 --version  # Should be 3.9+

# Verify virtual environment
source .venv/bin/activate
which python  # Should show .venv path

# Check dependencies
pip list | grep -E "(web3|solana|fastapi)"
```

### Missing API keys

```bash
# Check if secrets are loaded
python -c "
from src.config.settings import get_settings
s = get_settings()
print('Asgard key:', '✓' if s.asgard_api_key else '✗')
print('Solana key:', '✓' if s.solana_private_key else '✗')
print('HL key:', '✓' if s.hyperliquid_private_key else '✗')
"
```

### Dashboard can't connect to bot

```bash
# Check bot health
curl http://localhost:8000/health

# Verify bot is running
ps aux | grep python

# Check ports
lsof -i :8000  # Bot internal API
lsof -i :8080  # Dashboard
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

1. **Read the spec**: See [spec.md](spec.md) for full technical details
2. **Review architecture**: Check [spec-dashboard.md](spec-dashboard.md) for dashboard design
3. **Monitor performance**: Use the dashboard to track PnL and positions
4. **Set up alerts**: Configure Telegram/Discord webhooks (Phase 3)

---

## 💡 Tips

- **Start small**: Test with minimum position sizes first
- **Monitor funding rates**: Dashboard shows real-time funding PnL
- **Use pause**: Pause entry during volatile markets
- **Check health**: Use `/health` endpoint for monitoring
- **Backup state**: The bot saves state to `state.db`

---

**Need help?** Check [SECURITY.md](SECURITY.md) for security best practices and [README.md](README.md) for project overview.
