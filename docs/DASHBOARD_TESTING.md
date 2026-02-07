# Dashboard Testing Guide

How to run and test the Delta Neutral Bot Dashboard.

---

## Quick Start

### 1. Start the Dashboard Server

```bash
cd /Users/jo/Projects/BasisStrategy
source .venv/bin/activate
uvicorn src.dashboard.main:app --reload --port 8080
```

### 2. Open in Browser

```
http://localhost:8080
```

---

## First-Time Setup Flow

The dashboard has a 3-step setup wizard:

| Step | Action | What Happens |
|------|--------|--------------|
| 1 | **Login** | Click "Sign in with Privy" → Login with Google/Twitter/Email |
| 2 | **Wallets** | Auto-create Solana + Arbitrum wallets via Privy |
| 3 | **Exchange** | Optional API keys (skip - wallet auth works without) |
| → | **Dashboard** | Main interface appears |

---

## Dashboard Features to Test

### 🏠 Home Tab

| Feature | How to Test |
|---------|-------------|
| **Leverage Slider** | Drag from 2x to 4x → Watch rates update in real-time |
| **Asgard Rates** | Shows SOL, jitoSOL, jupSOL, INF on Kamino/Drift/Marginfi/Solend |
| **Hyperliquid** | Shows SOL-PERP funding rate (fetched from real API!) |
| **Open Position** | Click button → Select asset → Enter size → Submit |
| **Job Status** | After submit, modal shows progress through stages |

### ⚙️ Settings Tab

| Feature | How to Test |
|---------|-------------|
| **Save Preset 1** | Adjust settings → Click "Save to Preset 1" |
| **Save Preset 2** | Adjust settings → Click "Save to Preset 2" |
| **Load Preset** | Click Preset 1/2/3 → Settings change to saved values |
| **Reset Defaults** | Click "Reset to Defaults" → Back to factory settings |

### 🔴 Fund Wallets

| Feature | How to Test |
|---------|-------------|
| **Fund Button** | Click "Fund Wallets" on Home tab |
| **Copy Addresses** | Click "Copy" buttons next to wallet addresses |
| **Requirements** | Shows minimum required amounts |

---

## Testing the Position Opening Flow

1. **Click "Open Position"** on Home tab
2. **Select Asset** from dropdown (SOL, jitoSOL, jupSOL, INF)
3. **Enter Size** in USD (min $1,000)
4. **Click Submit**
5. **Watch Job Status Modal:**
   - "Fetching market data..."
   - "Running preflight checks..."
   - "Opening Asgard position..."
   - "Opening Hyperliquid position..."
6. **Result:**
   - ✓ Success: Position appears in list
   - ✗ Failure: Error message shown

**Note:** Actual trading requires:
- Bot running in background
- Wallets funded with USDC
- Proper configuration

---

## API Endpoints Available

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/rates?leverage=3.0` | Real Asgard + Hyperliquid rates |
| `POST /api/v1/positions/open` | Open position (async job) |
| `GET /api/v1/positions/jobs/{job_id}` | Check job status |
| `GET /api/v1/positions` | List open positions |
| `GET /api/v1/settings` | Get settings |
| `POST /api/v1/settings` | Save settings |

---

## Troubleshooting

### "Bot not available" error
- Normal if bot isn't running
- Dashboard works for setup and viewing rates
- Trading requires bot to be running

### Rates not loading
- Check internet connection
- Asgard API: 1 req/sec limit (public)
- Hyperliquid API: Public, no limit

### Position opening fails
- Expected if bot isn't running
- Check job status at `/api/v1/positions/jobs/{job_id}`

---

## File Locations

| Component | Path |
|-----------|------|
| Dashboard HTML | `src/dashboard/templates/dashboard.html` |
| Funding Page | `src/dashboard/templates/funding.html` |
| Setup Wizard | `src/dashboard/templates/setup/*.html` |
| Dashboard API | `src/dashboard/api/*.py` |
| Bot Bridge | `src/dashboard/bot_bridge.py` |

---

## 555 Tests Passing ✅

```bash
source .venv/bin/activate
pytest tests/unit/ -q
```
