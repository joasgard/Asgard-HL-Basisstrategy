# Delta Neutral Bot Control Center
## Technical Specification v1.0

---

## 1. Executive Summary

This document specifies a **Control Center / Dashboard** web interface for the Delta Neutral Funding Rate Arbitrage Bot. The dashboard provides real-time monitoring, control capabilities, alerting, and historical analytics for bot operations.

### Purpose

Transform the bot from a command-line only tool to a comprehensive trading platform with:
- **Real-time Monitoring**: Live positions, PnL, health metrics
- **Control Interface**: Pause/resume, emergency stops, parameter adjustments
- **Alerting System**: Multi-channel notifications (webhook/Telegram/Discord)
- **Analytics**: Historical performance, funding rate trends, trade history

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WEB DASHBOARD                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Status     │  │  Positions   │  │   Control    │  │  Analytics   │     │
│  │   Panel      │  │   Monitor    │  │   Panel      │  │   Charts     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ HTTPS/WSS
┌──────────────────────────────▼──────────────────────────────────────────────┐
│                           API SERVER (FastAPI)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  REST API    │  │ WebSocket    │  │   Alert      │  │   Auth       │     │
│  │  Endpoints   │  │  Broadcast   │  │   Engine     │  │   Layer      │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│      BOT CORE (async)    │  │    STATE DATABASE        │
│  ┌──────────────────┐    │  │  ┌──────────────────┐    │
│  │  DeltaNeutralBot │    │  │  │   SQLite (now)   │    │
│  │  - get_stats()   │◄───┼──┼──┤   PostgreSQL     │    │
│  │  - get_positions │    │  │  │   (future)       │    │
│  │  - pause/resume  │    │  │  └──────────────────┘    │
│  └──────────────────┘    │  └──────────────────────────┘
└──────────────────────────┘
```

---

## 2. Architecture

### 2.1 Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Backend** | FastAPI | Native async support, automatic OpenAPI docs, WebSocket support |
| **Frontend** | HTMX + Alpine.js | Lightweight, server-rendered, minimal JS complexity |
| **Styling** | Tailwind CSS | Utility-first, responsive, dark mode support |
| **Database** | SQLite (MVP) → PostgreSQL | SQLite for simplicity, upgrade path for scale |
| **Real-time** | WebSocket + Server-Sent Events | Native FastAPI support, efficient updates |
| **Auth** | JWT + API Keys | Stateless, compatible with existing admin_api_key |

### 2.2 Project Structure

**New Files (same repo):**

```
src/
├── core/                         # EXISTING: Bot code
├── dashboard/                    # NEW: Dashboard module
│   ├── __init__.py
│   ├── main.py                   # FastAPI app entry point
│   ├── config.py                 # Dashboard-specific settings
│   ├── auth.py                   # Authentication & authorization
│   ├── websocket.py              # WebSocket connection manager
│   ├── bot_bridge.py             # Communication with bot
│   ├── alerts/                   # Alerting system
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── channels/
│   │   │   ├── webhook.py
│   │   │   ├── telegram.py
│   │   │   └── discord.py
│   │   └── templates.py
│   ├── api/                      # REST API routes
│   │   ├── __init__.py
│   │   ├── status.py
│   │   ├── positions.py
│   │   ├── control.py
│   │   ├── config.py
│   │   └── history.py
│   ├── static/                   # CSS/JS assets
│   └── templates/                # HTML templates
├── shared/                       # NEW: Shared between bot and dashboard
│   ├── __init__.py
│   ├── schemas.py                # Pydantic models for API
│   └── events.py                 # Event type definitions
└── core/bot.py                   # MODIFIED: Add internal API endpoints

requirements/
├── base.txt                      # NEW: Common deps (pydantic)
├── bot.txt                       # NEW: Bot-specific
└── dashboard.txt                 # NEW: Dashboard-specific (fastapi, uvicorn)

docker/
├── docker-compose.yml            # MODIFIED: Add dashboard service
├── docker-compose.bot-only.yml   # NEW: Bot without dashboard
├── Dockerfile                    # EXISTING: Bot
└── Dockerfile.dashboard          # NEW: Dashboard
```

**Key Design:**
- `shared/` contains serializable models (Pydantic) used by both
- Bot exposes internal HTTP API on port 8000 (localhost only)
- Dashboard consumes this API and adds web layer on port 8080
- SQLite database shared via Docker volume (read-only for dashboard)

### 2.3 Integration with Existing Bot

**Architecture Decision: Same Repo, Separate Deployables**

The dashboard and bot live in the same repository but run as separate Docker containers:

```
BasisStrategy/                    # Single repo
├── src/
│   ├── core/                     # Bot code
│   ├── dashboard/                # Dashboard code  
│   └── shared/                   # Shared schemas
│       └── schemas.py
├── docker/
│   ├── docker-compose.yml        # Bot + Dashboard together
│   └── docker-compose.bot-only.yml  # Headless bot deploy
└── requirements/
    ├── base.txt                  # Common deps
    ├── bot.txt                   # Bot-specific
    └── dashboard.txt             # Dashboard-specific
```

**Communication Methods:**

| Scenario | Method | Details |
|----------|--------|---------|
| **MVP** | Shared SQLite + HTTP | Both containers mount same `state.db` read-only; dashboard queries bot via internal HTTP |
| **Future** | Message Queue | Redis/RabbitMQ for distributed deployments |

**Rationale:**
- ✅ Single repo keeps models in sync
- ✅ Separate containers = crash isolation
- ✅ Dashboard updates don't require bot restart
- ✅ Can deploy bot-only for headless operation
- ⚠️ Model changes require coordinated updates

```python
# dashboard/bot_bridge.py
class BotBridge:
    """
    Bridge between Dashboard and DeltaNeutralBot.
    
    Uses HTTP to communicate with bot's internal API (port 8000).
    Implements stale-data caching for availability over strict consistency.
    """
    
    def __init__(self, bot_api_url: str = "http://bot:8000"):
        self._api_url = bot_api_url
        self._client = httpx.AsyncClient(base_url=bot_api_url, timeout=5.0)
        self._cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 5.0  # 5 seconds stale data acceptable
        self._lock = asyncio.Lock()
        self._background_task = None
    
    async def start(self):
        """Start background cache refresh."""
        self._background_task = asyncio.create_task(self._background_refresh())
    
    async def _background_refresh(self):
        """Keep cache warm even without requests."""
        while True:
            await asyncio.sleep(5.0)
            try:
                await self.get_positions()
            except Exception as e:
                logger.error(f"Background refresh failed: {e}")
    
    async def get_positions(self) -> Dict[str, CombinedPosition]:
        """
        Get positions with caching.
        Returns stale data rather than hang on slow responses.
        """
        # Fast path: return cache if fresh
        if time.time() - self._cache_timestamp < self._cache_ttl:
            return self._cache.get("positions", {})
        
        # Slow path: refresh with timeout
        try:
            async with asyncio.timeout(2.0):
                async with self._lock:
                    response = await self._client.get("/internal/positions")
                    response.raise_for_status()
                    data = response.json()
                    positions = {k: CombinedPosition(**v) for k, v in data.items()}
                    self._cache["positions"] = positions
                    self._cache_timestamp = time.time()
                    return positions
        except asyncio.TimeoutError:
            logger.warning("Bot response timeout, returning cached positions")
            return self._cache.get("positions", {})
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            raise BotUnavailableError("Bot unavailable") from e
    
    async def get_stats(self) -> BotStats:
        """Get bot statistics via API."""
        response = await self._client.get("/internal/stats")
        response.raise_for_status()
        return BotStats(**response.json())
    
    async def pause(self, api_key: str, reason: str, scope: str) -> bool:
        """Pause bot operations via API."""
        response = await self._client.post(
            "/internal/control/pause",
            json={"api_key": api_key, "reason": reason, "scope": scope}
        )
        response.raise_for_status()
        return response.json()["success"]
    
    async def resume(self, api_key: str) -> bool:
        """Resume bot operations via API."""
        response = await self._client.post(
            "/internal/control/resume",
            json={"api_key": api_key}
        )
        response.raise_for_status()
        return response.json()["success"]
    
    async def health_check(self) -> bool:
        """Check if bot is healthy and responsive."""
        try:
            response = await self._client.get("/health", timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False
```

---

## 3. API Specification

### 3.1 REST API Endpoints

#### Status & Health

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/health` | Health check (dashboard + bot) | None |
| GET | `/api/v1/status` | Bot runtime status | API Key |
| GET | `/api/v1/stats` | Bot statistics | API Key |
| GET | `/api/v1/pause-state` | Current pause state | API Key |

```python
# Response: GET /api/v1/status
{
    "bot": {
        "running": true,
        "uptime_seconds": 86400,
        "uptime_formatted": "24:00:00",
        "environment": "production"
    },
    "pause_state": {
        "paused": false,
        "scope": "all",
        "reason": null,
        "paused_at": null,
        "paused_by": null,
        "active_breakers": []
    },
    "chains": {
        "solana": {"connected": true, "block_height": 123456789},
        "arbitrum": {"connected": true, "block_height": 987654321}
    }
}
```

#### Positions

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/positions` | List all positions | API Key |
| GET | `/api/v1/positions/{id}` | Get position details | API Key |
| GET | `/api/v1/positions/{id}/history` | Position history | API Key |

```python
# Response: GET /api/v1/positions
{
    "positions": [
        {
            "position_id": "pos_20250204000001",
            "asset": "SOL",
            "status": "open",
            "leverage": 3.0,
            "deployed_usd": 5000.00,
            "long_value_usd": 15000.00,
            "short_value_usd": 15000.00,
            "delta": 12.50,
            "delta_ratio": 0.0008,
            "asgard_hf": 0.28,
            "hyperliquid_mf": 0.15,
            "total_pnl_usd": 45.30,
            "funding_pnl_usd": 67.50,
            "opened_at": "2025-02-04T00:00:00Z",
            "hold_duration_hours": 12.5
        }
    ],
    "summary": {
        "total_positions": 1,
        "open_positions": 1,
        "closed_positions": 0,
        "total_pnl_usd": 45.30,
        "total_deployed_usd": 5000.00
    }
}
```

#### Control Operations

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/v1/control/pause` | Pause bot | Admin API Key |
| POST | `/api/v1/control/resume` | Resume bot | Admin API Key |
| POST | `/api/v1/control/emergency-stop` | Emergency stop all | Admin API Key |

```python
# Request: POST /api/v1/control/pause
{
    "reason": "Manual maintenance",
    "scope": "entry",  # "all", "entry", "exit", "asgard", "hyperliquid"
    "api_key": "secret_key"
}

# Response
{
    "success": true,
    "paused_at": "2025-02-04T12:00:00Z",
    "scope": "entry",
    "reason": "Manual maintenance"
}
```

#### Configuration

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/config` | Get configuration | API Key |
| PUT | `/api/v1/config` | Update configuration | Admin API Key |
| GET | `/api/v1/config/risk-limits` | Risk configuration | API Key |

```python
# Response: GET /api/v1/config
{
    "bot": {
        "poll_interval_seconds": 30,
        "scan_interval_seconds": 60,
        "max_concurrent_positions": 5,
        "min_opportunity_apy": 0.01,
        "enable_auto_exit": true,
        "enable_circuit_breakers": true
    },
    "risk": {
        "max_leverage": 4.0,
        "default_leverage": 3.0,
        "min_position_usd": 1000,
        "max_position_usd": 50000,
        "health_factor_warning": 0.20,
        "health_factor_critical": 0.10,
        "margin_fraction_warning": 0.10,
        "margin_fraction_critical": 0.05
    }
}
```

#### Historical Data

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/history/pnl` | PnL history | API Key |
| GET | `/api/v1/history/trades` | Trade history | API Key |
| GET | `/api/v1/history/funding` | Funding rate history | API Key |
| GET | `/api/v1/history/circuit-breakers` | Circuit breaker events | API Key |

```python
# Response: GET /api/v1/history/pnl?days=7
{
    "period": "7d",
    "data_points": [
        {
            "timestamp": "2025-02-04T00:00:00Z",
            "realized_pnl": 120.50,
            "unrealized_pnl": 45.30,
            "total_pnl": 165.80,
            "funding_pnl": 89.20,
            "position_pnl": 76.60
        }
    ],
    "summary": {
        "total_realized": 120.50,
        "total_unrealized": 45.30,
        "win_rate": 0.75,
        "avg_pnl_per_trade": 30.12
    }
}
```

#### Alerts

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/v1/alerts/config` | Alert configuration | Admin API Key |
| PUT | `/api/v1/alerts/config` | Update alert config | Admin API Key |
| POST | `/api/v1/alerts/test` | Test alert channels | Admin API Key |
| GET | `/api/v1/alerts/history` | Alert history | API Key |

### 3.2 WebSocket Endpoints

| Path | Description | Auth |
|------|-------------|------|
| `/ws/v1/feed` | Real-time data feed | JWT Token |

```python
# WebSocket Protocol: Snapshot + Delta Pattern

## Connection Flow

1. Client connects and subscribes with optional `last_seq`
2. Server sends full `snapshot` of current state
3. Server sends `delta` updates with sequence numbers
4. Client can request `catch_up` if reconnecting

## Message Types

# Client -> Server: Subscribe
{
    "action": "subscribe",
    "channels": ["positions", "pause_state"],
    "last_seq": 0  # 0 for fresh connection, or last known seq for reconnect
}

# Server -> Client: Initial Snapshot
{
    "type": "snapshot",
    "seq": 100,
    "timestamp": "2025-02-04T12:00:00Z",
    "data": {
        "positions": { /* full positions dict */ },
        "pause_state": { /* full pause state */ },
        "stats": { /* full stats */ }
    }
}

# Server -> Client: Delta Update (Position)
{
    "type": "position_update",
    "seq": 101,
    "timestamp": "2025-02-04T12:00:05Z",
    "data": {
        "position_id": "pos_20250204000001",
        "total_pnl_usd": 46.20,
        "asgard_hf": 0.279,
        "hyperliquid_mf": 0.148
    }
}

# Server -> Client: Pause State Change
{
    "type": "pause_state_change",
    "seq": 102,
    "timestamp": "2025-02-04T12:00:10Z",
    "data": {
        "paused": true,
        "scope": "entry",
        "reason": "Circuit breaker: negative_apy",
        "active_breakers": ["negative_apy"]
    }
}

# Server -> Client: Token Refresh Required
{
    "type": "token_refresh_required",
    "timestamp": "2025-02-04T12:00:30Z",
    "refresh_url": "/api/v1/auth/refresh"
}

# Client -> Server: Refresh Token
{
    "action": "refresh_token",
    "token": "new_jwt_token_here"
}

# Server -> Client: Heartbeat
{
    "type": "heartbeat",
    "seq": 103,
    "timestamp": "2025-02-04T12:00:30Z"
}

# Server -> Client: Catch-up (on reconnect with last_seq)
{
    "type": "catch_up",
    "from_seq": 95,
    "to_seq": 103,
    "events": [
        /* All events between from_seq and to_seq */
    ]
}
```

---

## 4. UI/UX Design

### 4.1 Layout Structure

```
┌─────────────────────────────────────────────────────────────────────┐
│  Logo    Dashboard    Positions    Analytics    Settings    User  │  ← Navigation
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  STATUS OVERVIEW                                            │   │  ← Status Cards
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │   │
│  │  │  Uptime  │ │ Positions│ │  PnL 24h │ │  Health  │       │   │
│  │  │ 24:00:00 │ │    3     │ │ +$123.45│ │   OK     │       │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐   │
│  │  ACTIVE POSITIONS        │  │  CONTROL PANEL               │   │
│  │  ┌────────────────────┐  │  │                              │   │
│  │  │ SOL  |  3x  | +$45 │  │  │  [Pause Entry] [Pause All]  │   │  ← Quick Actions
│  │  │ HF: 28%  MF: 15%   │  │  │                              │   │
│  │  └────────────────────┘  │  │  [Emergency Stop]            │   │
│  │  ┌────────────────────┐  │  │                              │   │
│  │  │jitoSOL| 3x | +$78 │  │  │  Status: RUNNING             │   │
│  │  │ HF: 25%  MF: 12%   │  │  │  Last Update: 2s ago        │   │
│  │  └────────────────────┘  │  │                              │   │
│  └──────────────────────────┘  └──────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  PnL CHART (24h / 7d / 30d)                                 │   │  ← Analytics
│  │                                                             │   │
│  │    ▲                                                        │   │
│  │  $ │    ╱╲      ╱╲                                         │   │
│  │    │   ╱  ╲    ╱  ╲________                                │   │
│  │    │__/    ╲__╱                                           │   │
│  │    └──────────────────────────────────────────▶            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  RECENT ACTIVITY                                            │   │  ← Audit Log
│  │  • 12:05:23 - Position opened: jitoSOL @ 3x                 │   │
│  │  • 12:00:00 - Funding payment received: $2.34               │   │
│  │  • 11:45:12 - Circuit breaker triggered: negative_apy       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Page Structure

| Page | Route | Description |
|------|-------|-------------|
| **Dashboard** | `/` | Main overview with status, positions, quick controls |
| **Positions** | `/positions` | Detailed position list with search/filter |
| **Position Detail** | `/positions/{id}` | Individual position details, history, PnL |
| **Analytics** | `/analytics` | Charts, performance metrics, funding trends |
| **Settings** | `/settings` | Configuration, alerts, user management |
| **Audit Log** | `/logs` | Complete action history |

### 4.3 Mobile Responsiveness

```
Mobile View (< 768px):
┌─────────────────────────┐
│  ☰  Delta Neutral Bot   │
├─────────────────────────┤
│  ┌───────────────────┐  │
│  │   STATUS CARDS    │  │  ← Horizontal scroll
│  │  [<<] [>>] [>>]   │  │
│  └───────────────────┘  │
│                         │
│  ┌───────────────────┐  │
│  │ CONTROL PANEL     │  │  ← Stacked layout
│  │ [Pause] [Stop]    │  │
│  └───────────────────┘  │
│                         │
│  ┌───────────────────┐  │
│  │ POSITIONS (3)     │  │  ← Collapsible list
│  │ ▼ SOL  +$45      │  │
│  │   HF: 28%        │  │
│  │ ▶ jitoSOL +$78   │  │
│  └───────────────────┘  │
└─────────────────────────┘
```

### 4.4 Color Scheme

| Element | Light Mode | Dark Mode |
|---------|------------|-----------|
| Background | `#ffffff` | `#0f172a` |
| Card Background | `#f8fafc` | `#1e293b` |
| Primary | `#3b82f6` | `#60a5fa` |
| Success (PnL+) | `#22c55e` | `#4ade80` |
| Danger (PnL-) | `#ef4444` | `#f87171` |
| Warning | `#f59e0b` | `#fbbf24` |
| Text Primary | `#1e293b` | `#f1f5f9` |
| Text Secondary | `#64748b` | `#94a3b8` |

---

## 5. Security Model

### 5.1 Authentication

Two authentication methods supported:

1. **API Key Authentication** (for programmatic access)
   - Header: `X-API-Key: <api_key>`
   - Reuses existing `admin_api_key` from bot configuration
   - Full read/write access

2. **JWT Authentication** (for web dashboard)
   - Login endpoint: `POST /api/v1/auth/login`
   - Token expires after 24 hours
   - Silent refresh via WebSocket before expiry

```python
# JWT Claims
{
    "sub": "admin",
    "role": "operator",  # viewer, operator, admin
    "permissions": ["read", "write"],
    "iat": 1707043200,
    "exp": 1707129600
}
```

**Token Refresh Flow:**
```javascript
// Client receives token_refresh_required 5 min before expiry
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "token_refresh_required") {
        fetch("/api/v1/auth/refresh", {method: "POST"})
            .then(r => r.json())
            .then(data => {
                ws.send(JSON.stringify({
                    action: "refresh_token",
                    token: data.access_token
                }));
            });
    }
};
```

### 5.2 Authorization Levels

Dashboard enforces RBAC; bot only validates admin_api_key.

| Role | Read | Control | Config | Alerts |
|------|------|---------|--------|--------|
| **Viewer** | ✅ All | ❌ | ❌ | View only |
| **Operator** | ✅ All | ✅ Pause Entry/Exit | View | View/Modify |
| **Admin** | ✅ All | ✅ All (inc. Emergency) | ✅ All | ✅ All |

**Proxy Pattern:**
```python
@app.post("/api/v1/control/pause")
async def pause_endpoint(
    request: PauseRequest,
    current_user: User = Depends(get_current_user)
):
    # 1. Dashboard enforces RBAC
    if current_user.role not in ["operator", "admin"]:
        raise HTTPException(403, "Operators or admins only")
    
    if request.scope == "all" and current_user.role != "admin":
        raise HTTPException(403, "Only admins can fully pause")
    
    # 2. Audit log who performed action
    await audit_log.record(
        user=current_user.username,
        action="pause",
        scope=request.scope,
        reason=request.reason
    )
    
    # 3. Proxy to bot with admin key (bot validates)
    result = await bot_bridge.pause(
        api_key=settings.bot_admin_key,
        reason=f"{current_user.username}: {request.reason}",
        scope=request.scope
    )
    
    return {"success": result}
```

### 5.3 Security Measures

```python
# Security configuration
dashboard_config = {
    # Rate limiting (per-user, application-level)
    "rate_limit": {
        "viewer": (100, 60),      # 100 requests per minute
        "operator": (200, 60),    # 200 per minute
        "admin": (500, 60),       # 500 per minute
        "login": (5, 300),        # 5 login attempts per 5 minutes
        "control": (10, 60)       # 10 control ops per minute
    },
    
    # CORS settings
    "cors": {
        "allowed_origins": ["https://dashboard.yourdomain.com"],
        "allow_credentials": True
    },
    
    # Security headers
    "headers": {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
    },
    
    # Session management
    "session": {
        "max_age": 86400,  # 24 hours
        "secure": True,
        "httponly": True,
        "samesite": "strict"
    }
}
```

### 5.4 Secret Handling

**Critical**: Trading secrets remain in `secrets/` directory, never exposed to web:

```python
# dashboard/config.py - Safe configuration
class DashboardSettings(BaseSettings):
    """Dashboard settings - NO trading secrets."""
    
    # Dashboard-specific secrets only
    jwt_secret: str = Field(
        default_factory=lambda: get_secret("DASHBOARD_JWT_SECRET", "dashboard_jwt.txt")
    )
    session_secret: str = Field(
        default_factory=lambda: get_secret("DASHBOARD_SESSION_SECRET", "dashboard_session.txt")
    )
    
    # Reference to bot admin key for control operations
    # Bot validates this internally - we don't use it directly
    admin_api_key_path: str = "secrets/admin_api_key.txt"
    
    # Trading secrets are NOT loaded here
    # - solana_private_key
    # - hyperliquid_private_key
    # - asgard_api_key
    # These remain in bot core only
```

---

## 6. Alerting System

### 6.1 Alert Types

| Alert | Severity | Condition | Default | Throttle |
|-------|----------|-----------|---------|----------|
| `funding_flip` | WARNING | Funding rate flipped positive | ✅ On | 5 min |
| `health_factor_warning` | WARNING | HF < 20% or MF < 10% | ✅ On | 5 min |
| `health_factor_critical` | CRITICAL | HF < 15% or MF < 8% | ✅ On | 1 min |
| `health_factor_emergency` | CRITICAL | HF < 10% or MF < 5% | ✅ On | **None** |
| `delta_drift` | WARNING | Delta ratio > 0.5% | ✅ On | 5 min |
| `lst_depeg` | CRITICAL | LST premium > 5% or discount > 2% | ✅ On | **None** |
| `circuit_breaker` | CRITICAL | Any circuit breaker triggered | ✅ On | **None** |
| `position_liquidation` | CRITICAL | Position near liquidation | ✅ On | **None** |
| `chain_outage` | CRITICAL | Solana or Arbitrum unreachable | ✅ On | 1 min |
| `transaction_failure` | WARNING | Transaction failed after retries | ✅ On | 5 min |
| `heartbeat` | INFO | Regular status update | ⏰ 1hr | N/A |
| `daily_pnl` | INFO | Daily PnL summary | ⏰ 00:00 UTC | N/A |

**Progressive Severity:** Health factor alerts escalate from warning → critical → emergency with increasing severity and decreasing throttle intervals.

### 6.2 Notification Channels

```python
# Alert configuration structure
alert_config = {
    "channels": {
        "webhook": {
            "enabled": True,
            "url": "https://hooks.slack.com/services/...",
            "events": ["critical", "warning"],
            "headers": {"Authorization": "Bearer ..."}
        },
        "telegram": {
            "enabled": True,
            "bot_token": "${TELEGRAM_BOT_TOKEN}",
            "chat_id": "${TELEGRAM_CHAT_ID}",
            "events": ["critical", "warning", "info"]
        },
        "discord": {
            "enabled": False,
            "webhook_url": "${DISCORD_WEBHOOK_URL}",
            "events": ["critical"]
        },
        "email": {
            "enabled": False,  # Future
            "smtp_host": "...",
            "to_address": "...",
            "events": ["critical"]
        }
    },
    "throttling": {
        "default_interval": 300,  # 5 minutes between same alert type
        "critical_bypass": True   # Critical alerts always sent
    }
}
```

### 6.3 Alert Templates

**Template Formatting Guidelines:**
- Use decimal format (0.25) for health factor, NOT percentage (25%)
- Always include liquidation threshold context
- Progressive alerts show escalation path

```python
TELEGRAM_TEMPLATES = {
    "funding_flip": """
⚠️ <b>Funding Rate Flip Detected</b>

Asset: {asset}
Previous: {previous_rate:.4%}
Current: {current_rate:.4%}
Position: {position_id}

Action: Monitoring for exit opportunity
""",
    
    "health_factor_warning": """
⚠️ <b>WARNING: Health Factor Declining</b>

Position: {position_id}
Asset: {asset}
Health Factor: {health_factor:.4f} (25%)
Margin Fraction: {margin_fraction:.4f} (15%)

Liquidation at: 0.00 (0%)
Escalates to CRITICAL at: 0.15 (15%)
""",
    
    "health_factor_critical": """
🚨 <b>CRITICAL: Health Factor Alert</b>

Position: {position_id}
Asset: {asset}
Health Factor: {health_factor:.4f} (15%)
Margin Fraction: {margin_fraction:.4f} (8%)

Liquidation at: 0.00 (0%)
Escalates to EMERGENCY at: 0.10 (10%)

<strong>Monitor closely - prepare to add collateral</strong>
""",
    
    "health_factor_emergency": """
🔴 <b>EMERGENCY: Liquidation Imminent</b>

Position: {position_id}
Asset: {asset}
Health Factor: {health_factor:.4f} ({health_factor_pct:.1f}%)
Margin Fraction: {margin_fraction:.4f} ({margin_fraction_pct:.1f}%)

Distance to liquidation: {distance_to_liquidation:.2%}
Estimated time: {estimated_time_to_liquidation}

<strong>ACTION REQUIRED: Add collateral or close position</strong>
""",
    
    "circuit_breaker": """
🔴 <b>Circuit Breaker Triggered</b>

Type: {breaker_type}
Reason: {reason}
Scope: {scope}
Time: {timestamp}

Bot operations have been paused.
Use /resume to restart after investigation.
""",
    
    "daily_pnl": """
📊 <b>Daily PnL Summary</b>

Date: {date}
Realized PnL: ${realized_pnl:,.2f}
Unrealized PnL: ${unrealized_pnl:,.2f}
Total PnL: ${total_pnl:,.2f}

Win Rate: {win_rate:.1%}
Total Trades: {total_trades}
"""
}
```

### 6.4 Progressive Severity Engine

```python
class AlertEngine:
    """
    Evaluates metrics and triggers alerts with progressive severity.
    Each severity level has its own throttle to prevent spam while
    ensuring rapid escalation when conditions worsen.
    """
    
    def __init__(self):
        self._last_alert = {}  # {(metric_key, severity): timestamp}
    
    async def check_health_factor(self, position: Position):
        hf = position.asgard.current_health_factor
        mf = position.hyperliquid.margin_fraction
        
        # Define severity levels with thresholds and throttles
        levels = [
            ("emergency", 0.10, 0.05, 0),      # No throttle
            ("critical", 0.15, 0.08, 60),       # 1 min
            ("warning", 0.20, 0.10, 300),       # 5 min
        ]
        
        for severity, hf_threshold, mf_threshold, throttle in levels:
            if hf < hf_threshold or mf < mf_threshold:
                metric_key = f"{position.id}_hf_{severity}"
                
                if await self._should_send_alert(metric_key, severity, throttle):
                    await self._send_alert(
                        alert_type="health_factor",
                        severity=severity,
                        position=position,
                        health_factor=hf,
                        margin_fraction=mf
                    )
                
                # Only trigger one severity level (highest)
                break
    
    async def _should_send_alert(self, metric_key: str, severity: str, throttle: int) -> bool:
        """Check if enough time has passed since last alert of this type/severity."""
        if throttle == 0:
            return True  # No throttle (emergency alerts)
        
        last_sent = self._last_alert.get((metric_key, severity), 0)
        if time.time() - last_sent < throttle:
            return False
        
        self._last_alert[(metric_key, severity)] = time.time()
        return True
```
```

---

## 7. Deployment Strategy

### 7.1 Docker Compose Integration

```yaml
# docker/docker-compose.yml additions

services:
  # Existing bot service...
  
  # ===========================================================================
  # Dashboard Service (NEW)
  # ===========================================================================
  dashboard:
    build:
      context: ..
      dockerfile: docker/Dockerfile.dashboard
    image: delta-neutral-dashboard:latest
    container_name: delta-neutral-dashboard
    restart: unless-stopped
    
    environment:
      - DASHBOARD_ENV=production
      - DASHBOARD_HOST=0.0.0.0
      - DASHBOARD_PORT=8080
      - BOT_API_URL=http://bot:8000  # Internal communication
      - JWT_SECRET=${DASHBOARD_JWT_SECRET}
      - SESSION_SECRET=${DASHBOARD_SESSION_SECRET}
      
      # Alert channels
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}
      - ALERT_WEBHOOK_URL=${ALERT_WEBHOOK_URL:-}
      - DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL:-}
    
    volumes:
      - bot-data:/app/data:ro  # Read-only access to bot state
      - dashboard-data:/app/dashboard/data
    
    ports:
      - "8080:8080"
    
    networks:
      - bot-network
    
    depends_on:
      - bot
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # ===========================================================================
  # Reverse Proxy (Caddy/Nginx) for SSL termination
  # ===========================================================================
  proxy:
    image: caddy:2-alpine
    container_name: delta-neutral-proxy
    restart: unless-stopped
    
    ports:
      - "80:80"
      - "443:443"
    
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
      - caddy-config:/config
    
    networks:
      - bot-network
    
    depends_on:
      - dashboard

volumes:
  # Existing volumes...
  dashboard-data:
    driver: local
  caddy-data:
    driver: local
  caddy-config:
    driver: local
```

### 7.2 Caddyfile (Automatic HTTPS)

```caddyfile
# docker/Caddyfile
# Note: Rate limiting handled at application level, not Caddy

dashboard.yourdomain.com {
    # Automatic HTTPS (Let's Encrypt)
    tls admin@yourdomain.com
    
    # Security headers
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        X-XSS-Protection "1; mode=block"
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    }
    
    # WebSocket support
    @websockets {
        header Connection *Upgrade*
        header Upgrade websocket
    }
    reverse_proxy @websockets dashboard:8080
    
    # Regular requests
    reverse_proxy dashboard:8080
}
```

### 7.3 Dockerfile (Dashboard)

```dockerfile
# docker/Dockerfile.dashboard
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DASHBOARD_ENV=production

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r dashboard && useradd -r -g dashboard -s /bin/false dashboard

# Install Python deps
COPY requirements-dashboard.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-dashboard.txt

WORKDIR /app

# Copy dashboard code
COPY src/dashboard/ ./src/dashboard/
COPY src/core/ ./src/core/  # Shared models
COPY src/models/ ./src/models/
COPY src/config/ ./src/config/
COPY src/state/ ./src/state/
COPY src/utils/ ./src/utils/

# Create data directory
RUN mkdir -p /app/data && chown -R dashboard:dashboard /app

USER dashboard

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f "http://localhost:8080/api/v1/health" --max-time 4 || exit 1

CMD ["uvicorn", "src.dashboard.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 7.4 Environment Variables

```bash
# .env.example additions for dashboard

# Dashboard Configuration
DASHBOARD_ENV=production
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8080
DASHBOARD_JWT_SECRET=change-me-in-production-min-32-chars-long
DASHBOARD_SESSION_SECRET=another-secret-min-32-chars-long

# Alert Channels (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ALERT_WEBHOOK_URL=
DISCORD_WEBHOOK_URL=

# Domain (for Caddy)
DASHBOARD_DOMAIN=dashboard.yourdomain.com
```

---

## 8. Implementation Phases

### Phase 1: MVP - Foundation

**Goal**: Essential monitoring and emergency controls

| Feature | Priority | Description |
|---------|----------|-------------|
| FastAPI server | Required | Core REST API framework |
| Status endpoints | Required | Bot health, pause state, basic stats |
| Position list | Required | Active positions with key metrics |
| Pause/Resume controls | Required | Emergency stop capability via API |
| API Key auth | Required | Secure access using existing admin key |
| WebSocket feed | Required | Real-time position/pause updates |
| Basic HTML UI | Required | Functional dashboard, minimal styling |
| Docker service | Required | Container deployment via compose |

**Success Criteria**:
- Dashboard accessible via browser
- Real-time position monitoring works
- Can pause/resume bot operations
- Survives bot restarts gracefully

---

### Phase 2: Enhanced UX - Visualization

**Goal**: Rich data presentation and mobile support

| Feature | Priority | Description |
|---------|----------|-------------|
| PnL charts | High | Interactive Chart.js visualizations |
| Position detail view | High | Individual position drill-down |
| Historical data API | High | Time-series queries for charts |
| Audit log viewer | High | Action history with filtering |
| Mobile-responsive UI | High | Works on phones/tablets |
| Dark mode | Medium | Toggle between light/dark themes |
| Funding rate charts | Medium | Visualize funding trends |
| Export functionality | Low | CSV/JSON data export |

**Success Criteria**:
- Charts render correctly on mobile
- Can view 7/30/90 day PnL history
- Position detail shows full lifecycle

---

### Phase 3: Alerting - Notifications

**Goal**: Proactive monitoring and external notifications

| Feature | Priority | Description |
|---------|----------|-------------|
| Alert engine | High | Event evaluation and trigger logic |
| Webhook channel | High | Generic HTTP POST notifications |
| Telegram bot | High | Bot commands and push notifications |
| Alert configuration API | High | CRUD for alert rules |
| Alert history | Medium | Log of all sent alerts |
| Discord webhook | Medium | Discord channel integration |
| Alert templates | Medium | Customizable message formats |
| Throttling logic | Medium | Prevent alert spam |

**Success Criteria**:
- Critical alerts sent within 5 seconds of trigger
- Telegram bot responds to /status command
- Can configure alerts via dashboard UI

---

### Phase 4: Production - Security & Scale

**Goal**: Enterprise-ready deployment and access control

| Feature | Priority | Description |
|---------|----------|-------------|
| JWT authentication | High | Session-based web auth |
| User management | High | Multi-user with role-based access |
| HTTPS/Caddy | High | Automatic SSL termination |
| Rate limiting | High | API throttling and abuse prevention |
| Security headers | High | HSTS, CSP, XSS protection |
| PostgreSQL support | Medium | Migrate from SQLite |
| Backup automation | Medium | Scheduled DB backups |
| Audit trail | Medium | Complete admin action logging |
| SSO integration | Low | OAuth2/LDAP support |

**Success Criteria**:
- Passes security audit (headers, auth, rate limits)
- Supports 3+ concurrent users with different roles
- Zero-downtime database migration path documented

---

## 9. Database Schema (MVP - SQLite)

### 9.1 SQLite Configuration

```python
# src/state/persistence.py - WAL mode for better concurrency

class StatePersistence:
    async def setup(self):
        self._db = await aiosqlite.connect(self.db_path)
        
        # Enable WAL mode for better concurrency
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA busy_timeout=5000")  # 5 seconds
        
        await self._create_tables()
```

### 9.2 New Tables for Dashboard

```sql
-- User management (Phase 4)
CREATE TABLE dashboard_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',  -- viewer, operator, admin
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- Alert configuration with progressive severity
CREATE TABLE alert_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    severity TEXT NOT NULL,  -- info, warning, critical
    channels TEXT,  -- JSON array of channel names
    -- Progressive throttling by severity
    throttle_seconds INTEGER DEFAULT 300,
    no_throttle_on_escalation BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Alert history
CREATE TABLE alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    metric_key TEXT,  -- For per-metric throttling (e.g., "pos_123_hf_critical")
    message TEXT NOT NULL,
    channels_sent TEXT,  -- JSON object with delivery status
    acknowledged BOOLEAN DEFAULT 0,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Time-series metrics with downsampling support
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_type TEXT NOT NULL,  -- pnl, funding_rate, health_factor, etc.
    value REAL NOT NULL,
    metadata TEXT,  -- JSON with context
    resolution TEXT DEFAULT '1min',  -- 1min, 5min, 1hour, 1day
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Downsampled metrics (automatically populated)
CREATE TABLE metrics_downsampled (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_type TEXT NOT NULL,
    resolution TEXT NOT NULL,  -- 5min, 1hour, 1day
    timestamp TIMESTAMP NOT NULL,
    avg_value REAL NOT NULL,
    min_value REAL NOT NULL,
    max_value REAL NOT NULL,
    count INTEGER NOT NULL
);

-- Create indexes
CREATE INDEX idx_alert_history_type ON alert_history(alert_type);
CREATE INDEX idx_alert_history_time ON alert_history(created_at);
CREATE INDEX idx_metrics_type_time ON metrics(metric_type, timestamp);
CREATE INDEX idx_metrics_resolution ON metrics(metric_type, resolution, timestamp);
CREATE INDEX idx_metrics_downsampled_lookup ON metrics_downsampled(metric_type, resolution, timestamp);
```

### 9.3 Metrics Retention and Downsampling

```python
# src/dashboard/metrics_retention.py

class MetricsRetentionManager:
    """
    Automated retention policy:
    - 7 days at 1-minute resolution (10,080 points)
    - 30 days at 5-minute resolution (8,640 points)
    - 90 days at 1-hour resolution (2,160 points)
    - 1 year at 1-day resolution (365 points)
    """
    
    RETENTION_CONFIG = [
        (7, "1min", None),      # Keep raw for 7 days
        (30, "5min", "5min"),   # Days 8-30: 5-min aggregates
        (90, "1hour", "1hour"), # Days 31-90: hourly aggregates
        (365, "1day", "1day"),  # Days 91-365: daily aggregates
    ]
    
    async def cleanup_old_metrics(self):
        """Run daily at 3 AM via APScheduler."""
        async with aiosqlite.connect(self.db_path) as db:
            # Delete data older than 1 year
            cutoff = datetime.utcnow() - timedelta(days=365)
            await db.execute(
                "DELETE FROM metrics WHERE timestamp < ?",
                (cutoff.isoformat(),)
            )
            
            # Downsample data based on retention config
            for days, target_res, source_res in self.RETENTION_CONFIG:
                await self._downsample_period(db, days, target_res, source_res)
            
            # Vacuum to reclaim space
            await db.execute("VACUUM")
            await db.commit()
    
    async def _downsample_period(self, db, age_days: int, interval: str, source: str):
        """Downsample metrics to specified resolution."""
        window_start = datetime.utcnow() - timedelta(days=age_days + 7)
        window_end = datetime.utcnow() - timedelta(days=age_days)
        
        interval_sql = {
            "5min": "%Y-%m-%d %H:%M",
            "1hour": "%Y-%m-%d %H:00",
            "1day": "%Y-%m-%d 00:00"
        }.get(interval, "%Y-%m-%d %H:%M")
        
        await db.execute(f"""
            INSERT INTO metrics_downsampled 
                (metric_type, resolution, timestamp, avg_value, min_value, max_value, count)
            SELECT 
                metric_type,
                ? as resolution,
                strftime('{interval_sql}', timestamp) as interval_start,
                AVG(value) as avg_value,
                MIN(value) as min_value,
                MAX(value) as max_value,
                COUNT(*) as count
            FROM metrics
            WHERE timestamp BETWEEN ? AND ?
              AND resolution = '1min'  -- Only downsample from raw
            GROUP BY metric_type, interval_start
        """, (interval, window_start.isoformat(), window_end.isoformat()))
        
        # Delete original high-frequency data
        await db.execute("""
            DELETE FROM metrics 
            WHERE timestamp BETWEEN ? AND ?
              AND resolution = '1min'
        """, (window_start.isoformat(), window_end.isoformat()))
```

### 9.4 Migration Path to PostgreSQL

```python
# Future migration script
async def migrate_to_postgres():
    """Migrate from SQLite to PostgreSQL."""
    # 1. Export all SQLite data
    # 2. Import to PostgreSQL
    # 3. Update connection strings
    # 4. Validate data integrity
    pass
```

---

## 10. Performance Considerations

### 10.1 Resource Requirements

| Component | CPU | Memory | Storage |
|-----------|-----|--------|---------|
| Dashboard | 0.5 cores | 512MB | 1GB |
| WebSocket (100 conn) | +0.2 cores | +100MB | - |
| Database (SQLite) | - | - | 100MB/month |

### 10.2 WebSocket Optimizations

**Message Batching and Binary Protocol:**

```python
import msgpack  # 40% smaller than JSON

class OptimizedWebSocketManager:
    def __init__(self):
        self._connections = set()
        self._batch_queue = []
        self._batch_timer = None
        self._use_msgpack = True
        self._max_connections = 500
    
    async def connect(self, websocket: WebSocket):
        """Limit concurrent connections."""
        if len(self._connections) >= self._max_connections:
            await websocket.close(code=1013, reason="Server overload")
            return
        
        await websocket.accept()
        self._connections.add(websocket)
    
    async def broadcast(self, message: dict, urgent: bool = False):
        """
        Batch non-urgent messages (100ms window).
        Send urgent messages immediately.
        """
        if urgent:
            await self._send_immediately(message)
        else:
            self._batch_queue.append(message)
            
            if self._batch_timer is None:
                self._batch_timer = asyncio.create_task(
                    self._flush_batch_after(0.1)
                )
    
    async def _send_to_all(self, message: dict):
        """Send with msgpack compression."""
        if self._use_msgpack:
            payload = msgpack.packb(message, use_bin_type=True)
        else:
            payload = json.dumps(message).encode()
        
        # Concurrent send
        tasks = [self._send_safe(conn, payload) for conn in self._connections]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clean up disconnected clients
        for conn, result in zip(list(self._connections), results):
            if isinstance(result, Exception):
                self._connections.discard(conn)
```

**Benchmarks:**
- JSON payload: ~200 bytes per position update
- Msgpack payload: ~120 bytes (40% reduction)
- Batching 10 updates: 1 frame instead of 10

### 10.3 Metrics Query Optimization

**Auto-downsampling by query range:**

```python
class MetricsQuery:
    async def get_pnl_history(self, days: int, resolution: str = "auto"):
        """
        Automatically select appropriate resolution:
        - ≤1 day: 1-minute resolution
        - ≤7 days: 5-minute resolution
        - ≤30 days: 1-hour resolution
        - >30 days: 1-day resolution
        """
        if resolution == "auto":
            resolution = self._select_resolution(days)
        
        # Query from pre-aggregated tables for large ranges
        table = "metrics_downsampled" if resolution != "1min" else "metrics"
        
        query = f"""
            SELECT timestamp, avg_value as value
            FROM {table}
            WHERE metric_type = 'pnl'
              AND resolution = ?
              AND timestamp > datetime('now', '-{days} days')
            ORDER BY timestamp
            LIMIT 2000  -- Hard limit for browser performance
        """
        
        return await self._execute(query, (resolution,))
```

### 10.4 Caching Strategy

```python
# src/dashboard/cache.py

from functools import wraps
import time

class TimedCache:
    """Simple TTL cache for dashboard data."""
    
    def __init__(self, default_ttl: float = 5.0):
        self._cache = {}
        self._ttl = default_ttl
    
    def get(self, key: str):
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            del self._cache[key]
        return None
    
    def set(self, key: str, value, ttl: float = None):
        expiry = time.time() + (ttl or self._ttl)
        self._cache[key] = (value, expiry)
    
    def cached(self, ttl: float = None):
        """Decorator for caching function results."""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                key = f"{func.__name__}:{args}:{kwargs}"
                cached = self.get(key)
                if cached is not None:
                    return cached
                result = await func(*args, **kwargs)
                self.set(key, result, ttl)
                return result
            return wrapper
        return decorator

# Usage:
cache = TimedCache()

@cache.cached(ttl=5.0)
async def get_positions():
    return await bot_bridge.get_positions()
```

---

## 11. Error Handling & Resilience

### 11.1 Bot Unavailability Handling

**Graceful degradation when bot is restarting:**

```python
@app.get("/api/v1/positions")
async def get_positions():
    try:
        positions = await bot_bridge.get_positions()
        return {
            "positions": positions,
            "source": "live",
            "timestamp": datetime.utcnow().isoformat()
        }
    except BotUnavailableError:
        # Return 503 with cached data if available
        cached = await get_cached_positions()
        return JSONResponse(
            status_code=503,
            content={
                "error": "Bot unavailable",
                "message": "Trading bot is starting up or recovering",
                "retry_after": 5,
                "cached_data": cached,
                "cached_at": cached.get("timestamp") if cached else None
            }
        )

@app.get("/api/v1/status")
async def get_status():
    """
    Return detailed status including bot startup state.
    """
    bot_health = await bot_bridge.health_check()
    bot_state = await bot_bridge.get_bot_state() if bot_health else "unavailable"
    
    return {
        "dashboard": {"status": "healthy", "version": "1.0.0"},
        "bot": {
            "state": bot_state,  # starting, recovering, running, degraded
            "healthy": bot_health,
            "recovery_progress": await bot_bridge.get_recovery_progress() 
                if bot_state == "recovering" else None
        }
    }
```

### 11.2 WebSocket Resilience

**Event sourcing with sequence numbers:**

```python
class EventStore:
    """
    Keeps last 10,000 events in memory for catch-up.
    Production: Use Redis Stream or database.
    """
    
    def __init__(self, max_events: int = 10000):
        self._events = deque(maxlen=max_events)
        self._sequence = 0
    
    def append(self, event: dict) -> int:
        self._sequence += 1
        event["seq"] = self._sequence
        event["timestamp"] = datetime.utcnow().isoformat()
        self._events.append(event)
        return self._sequence
    
    def get_since(self, last_seq: int) -> List[dict]:
        """Get all events after given sequence number."""
        return [e for e in self._events if e["seq"] > last_seq]

class ResilientWebSocketManager:
    async def handle_connection(self, websocket: WebSocket):
        await websocket.accept()
        
        # Wait for subscription message
        msg = await websocket.receive_json()
        last_seq = msg.get("last_seq", 0)
        
        # Send snapshot
        snapshot = await self._build_snapshot()
        snapshot["seq"] = self._event_store.current_seq()
        await websocket.send_json(snapshot)
        
        # Send missed events if reconnecting
        if last_seq > 0:
            missed = self._event_store.get_since(last_seq)
            if missed:
                await websocket.send_json({
                    "type": "catch_up",
                    "from_seq": last_seq,
                    "events": missed
                })
        
        # Subscribe to new events
        self._add_subscriber(websocket)
```

### 11.3 Circuit Breaker for External Services

```python
class CircuitBreaker:
    """
    Prevents cascading failures when external services (bot, Telegram) are down.
    """
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failures = 0
        self._last_failure = 0
        self._state = "closed"  # closed, open, half-open
    
    @property
    def allow_request(self) -> bool:
        if self._state == "open":
            if time.time() - self._last_failure > self._recovery_timeout:
                self._state = "half-open"
                return True
            return False
        return True
    
    def record_success(self):
        self._failures = 0
        self._state = "closed"
    
    def record_failure(self):
        self._failures += 1
        self._last_failure = time.time()
        
        if self._failures >= self._failure_threshold:
            self._state = "open"
            logger.warning(f"Circuit breaker opened for {self}")

# Usage in alert channels:
class TelegramChannel:
    def __init__(self):
        self._circuit_breaker = CircuitBreaker(failure_threshold=3)
    
    async def send(self, message: str):
        if not self._circuit_breaker.allow_request:
            logger.warning("Telegram circuit open, dropping message")
            return
        
        try:
            await self._bot.send_message(message)
            self._circuit_breaker.record_success()
        except Exception:
            self._circuit_breaker.record_failure()
            raise
```

---

## 12. Testing Strategy

### 11.1 Test Coverage

```python
# tests/dashboard/test_api.py
async def test_get_status(client):
    """Test status endpoint."""
    response = await client.get("/api/v1/status", headers={"X-API-Key": "test_key"})
    assert response.status_code == 200
    data = response.json()
    assert "bot" in data
    assert "pause_state" in data

async def test_pause_unauthorized(client):
    """Test pause requires valid API key."""
    response = await client.post("/api/v1/control/pause", json={
        "reason": "Test",
        "api_key": "wrong_key"
    })
    assert response.status_code == 403

# tests/dashboard/test_websocket.py
async def test_websocket_feed(client):
    """Test WebSocket real-time updates."""
    async with client.websocket_connect("/ws/v1/feed") as ws:
        # Subscribe
        await ws.send_json({"action": "subscribe", "channels": ["positions"]})
        
        # Wait for position update
        msg = await ws.receive_json()
        assert msg["type"] == "position_update"
```

### 11.2 Integration Tests

```python
# tests/dashboard/test_integration.py
async def test_full_position_lifecycle():
    """Test position appears in dashboard after creation."""
    # 1. Open position via bot
    position = await bot.open_position(opportunity)
    
    # 2. Wait for WebSocket broadcast
    await asyncio.sleep(0.1)
    
    # 3. Verify position appears in API
    response = await dashboard_client.get("/api/v1/positions")
    assert position.position_id in [p["position_id"] for p in response.json()["positions"]]
```

---

## 12. Structured Logging & Observability

### 12.1 Log Format

**JSON structured logs with correlation IDs:**

```python
# src/dashboard/logging_config.py
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ]
)

# Middleware to add correlation ID
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        user_agent=request.headers.get("user-agent"),
        client_ip=request.client.host
    )
    
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response
```

**Log output format:**
```json
{
  "timestamp": "2025-02-04T12:00:00.000Z",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "level": "info",
  "event": "Position opened",
  "position_id": "pos_123",
  "asset": "SOL",
  "user": "admin",
  "service": "dashboard"
}
```

### 12.2 Health Check Endpoint

**Comprehensive health check with dependency status:**

```python
@app.get("/api/v1/health")
async def health_check():
    """
    Kubernetes-style health check with dependency verification.
    """
    checks = {
        "dashboard": {"status": "healthy", "response_time_ms": 0},
        "bot_api": {"status": "unknown", "response_time_ms": 0},
        "database": {"status": "unknown", "response_time_ms": 0},
    }
    
    overall_status = "healthy"
    
    # Check bot API
    try:
        start = time.time()
        bot_healthy = await bot_bridge.health_check()
        checks["bot_api"]["response_time_ms"] = int((time.time() - start) * 1000)
        checks["bot_api"]["status"] = "healthy" if bot_healthy else "degraded"
        if not bot_healthy:
            overall_status = "degraded"
    except Exception as e:
        checks["bot_api"]["status"] = "unhealthy"
        checks["bot_api"]["error"] = str(e)
        overall_status = "degraded"
    
    # Check database
    try:
        start = time.time()
        await db.execute("SELECT 1")
        checks["database"]["response_time_ms"] = int((time.time() - start) * 1000)
        checks["database"]["status"] = "healthy"
    except Exception as e:
        checks["database"]["status"] = "unhealthy"
        overall_status = "unhealthy"
    
    status_code = 200 if overall_status in ["healthy", "degraded"] else 503
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "checks": checks
        }
    )
```

---

## 13. Open Questions

| Question | Context | Recommendation |
|----------|---------|----------------|
| Single vs separate process? | Dashboard in bot process or separate? | ✅ **Decided**: Separate containers with HTTP API |
| SQLite limits? | Will SQLite handle time-series data? | ✅ **Decided**: SQLite + WAL mode + downsampling, migrate to PostgreSQL when WAL > 500MB |
| Read-only mode? | Should dashboard work during bot restart? | ✅ **Decided**: Graceful degradation with stale data, 503 status, recovery progress |
| Multi-bot support? | Single dashboard for multiple bots? | Postpone to v2.0 |

---

## 14. Decision Summary

This section summarizes key architectural decisions from `dashboard_questions.md`:

| Area | Decision | Rationale |
|------|----------|-----------|
| **Architecture** | Same repo, separate containers | Shared models, crash isolation, independent deployment |
| **Bot Communication** | HTTP API with 5s stale-data cache | Availability over strict consistency |
| **WebSocket** | Snapshot + delta with sequence numbers | Handles reconnections gracefully |
| **Auth** | Dashboard proxies, enforces RBAC | Bot keeps simple auth, audit trail in dashboard |
| **Database** | SQLite WAL mode + automated downsampling | Simple MVP, clear migration path |
| **Alerts** | Progressive severity, no throttle on emergency | Rapid escalation when conditions worsen |
| **Performance** | Msgpack + batching + auto-downsampling | Efficient real-time updates |
| **Errors** | Circuit breakers + graceful degradation | Prevents cascading failures |
| **Logs** | JSON structured with correlation IDs | Observable, traceable requests |

---

---

## Appendix A: API Response Examples

### Full Position Detail

```json
{
  "position_id": "pos_20250204000001",
  "asset": "SOL",
  "protocol": "marginfi",
  "status": "open",
  "leverage": 3.0,
  "created_at": "2025-02-04T00:00:00Z",
  "hold_duration_hours": 12.5,
  
  "sizing": {
    "deployed_usd": 5000.00,
    "position_size_usd": 15000.00,
    "collateral_usd": 5000.00,
    "borrowed_usd": 10000.00
  },
  
  "asgard": {
    "position_pda": "ABC123...",
    "collateral_usd": 5000.00,
    "token_a_amount": 47.5,
    "entry_price": 105.25,
    "current_price": 106.10,
    "current_health_factor": 0.28,
    "liquidation_price": 75.20
  },
  
  "hyperliquid": {
    "size_sol": -47.5,
    "entry_px": 105.30,
    "mark_px": 106.15,
    "leverage": 3.0,
    "margin_used": 1666.67,
    "margin_fraction": 0.15,
    "liquidation_px": 140.50
  },
  
  "pnl": {
    "long_pnl": 40.38,
    "short_pnl": -40.38,
    "position_pnl": 0.00,
    "funding_pnl": 45.30,
    "total_pnl": 45.30,
    "total_pnl_pct": 0.0091
  },
  
  "risk": {
    "delta": 12.50,
    "delta_ratio": 0.0008,
    "health_status": "healthy",
    "distance_to_liquidation": 0.32
  }
}
```

### Circuit Breaker History

```json
{
  "circuit_breakers": [
    {
      "breaker_type": "negative_apy",
      "triggered_at": "2025-02-04T08:30:00Z",
      "reason": "Funding flipped positive: 0.001%",
      "scope": "entry",
      "auto_recovery": true,
      "cooldown_seconds": 1800,
      "recovery_time": "2025-02-04T09:00:00Z",
      "resolved_at": "2025-02-04T09:00:00Z",
      "resolved_by": "auto"
    }
  ]
}
```

---

*Document Version: 1.1*  
*Last Updated: 2026-02-05*  
*Target Release: v1.2 (Dashboard MVP)*

---

## Appendix B: Dashboard Questions Reference

Detailed Q&A with recommendations is maintained in `dashboard_questions.md`. This document contains:
- 23 deep-dive questions
- Code examples for each recommendation
- Trade-off analysis
- Implementation guidance

Review `dashboard_questions.md` before making architectural changes.
