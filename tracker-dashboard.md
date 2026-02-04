# Dashboard Implementation Tracker

**Project:** Delta Neutral Bot Control Center / Dashboard  
**Spec Version:** 1.1 (2026-02-05)  
**Base Bot:** Phases 1-9 Complete (686 tests passing)

This document tracks the implementation of the web dashboard for the Delta Neutral Funding Rate Arbitrage Bot. It serves as a context transfer document for future agents.

---

## Executive Summary

**Last Updated:** 2026-02-05

### Current Status: 🟡 NOT STARTED

The dashboard specification is finalized. Implementation has not begun.

### Implementation Phases

| Phase | Goal | Key Deliverables | Status |
|-------|------|------------------|--------|
| **Phase 1** | Foundation | FastAPI server, status endpoints, position list, pause/resume, WebSocket | `[ ]` |
| **Phase 2** | Enhanced UX | PnL charts, mobile UI, dark mode, position detail | `[ ]` |
| **Phase 3** | Alerting | Telegram bot, webhooks, alert engine, throttling | `[ ]` |
| **Phase 4** | Production | JWT auth, HTTPS, rate limiting, multi-user | `[ ]` |

### Status Legend
- `[ ]` Not started
- `[~]` In progress
- `[x]` Complete
- `[!]` Blocked/Issue
- `[?]` Needs review/decision

---

## Architecture Decisions (READ FIRST)

Before implementing, understand these key decisions from `spec-dashboard.md` and `dashboard_questions.md`:

### 1. Same Repo, Separate Deployables
- Dashboard code lives in `src/dashboard/`
- Bot and dashboard are separate Docker containers
- Shared Pydantic models in `src/shared/schemas.py`
- Communication via HTTP API (BotBridge pattern)

### 2. Availability Over Consistency
- BotBridge uses 5-second stale-data cache
- Returns cached data on timeout rather than hang
- Background refresh keeps cache warm

### 3. WebSocket: Snapshot + Delta
- New connections receive full snapshot first
- Then delta updates with sequence numbers
- Catch-up mechanism for reconnections

### 4. Security: RBAC Proxy Pattern
- Dashboard enforces roles (viewer/operator/admin)
- Dashboard proxies requests to bot with admin key
- Bot only validates admin_api_key
- Audit trail captures actual user (not just bot)

### 5. SQLite with Downsampling
- WAL mode for concurrency (PRAGMA journal_mode=WAL)
- Automated retention: 7d @ 1min → 30d @ 5min → 90d @ 1hr → 1y @ 1d
- Vacuum daily at 3 AM
- Migrate to PostgreSQL when WAL > 500MB

### 6. Progressive Severity Alerts
- Health factor: warning (5min throttle) → critical (1min) → emergency (no throttle)
- Emergency alerts (liquidation imminent) bypass throttling
- Per-metric throttling keys prevent cross-alert suppression

---

## Phase 1: MVP - Foundation

**Goal:** Essential monitoring and emergency controls

**Prerequisites:**
- Bot phases 1-9 complete (✅ Done)
- Docker and docker-compose installed
- Understanding of FastAPI and async Python

---

### Task 1.1: Project Structure Setup
**Status:** `[ ]`  
**Priority:** Critical  
**Dependencies:** None

**Actions:**

1. **Create directory structure:**
```
src/
├── dashboard/                    # NEW
│   ├── __init__.py
│   ├── main.py                   # FastAPI entry point
│   ├── config.py                 # Dashboard settings
│   ├── auth.py                   # JWT + API key auth
│   ├── bot_bridge.py             # HTTP client to bot
│   ├── websocket.py              # WS connection manager
│   ├── cache.py                  # Timed cache decorator
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── rate_limit.py         # Per-user rate limiting
│   │   └── logging.py            # Correlation ID middleware
│   ├── api/
│   │   ├── __init__.py
│   │   ├── status.py             # Health, status, stats
│   │   ├── positions.py          # Position endpoints
│   │   ├── control.py            # Pause/resume/emergency
│   │   ├── config.py             # Bot config endpoints
│   │   └── history.py            # Historical data
│   ├── alerts/
│   │   ├── __init__.py
│   │   ├── engine.py             # Alert evaluation
│   │   ├── channels/
│   │   │   ├── __init__.py
│   │   │   ├── telegram.py
│   │   │   ├── webhook.py
│   │   │   └── discord.py
│   │   └── templates.py          # Alert messages
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── images/
│   └── templates/
│       ├── base.html
│       ├── dashboard.html
│       ├── positions.html
│       └── components/
│           ├── status_card.html
│           ├── position_row.html
│           └── control_panel.html
├── shared/                       # NEW
│   ├── __init__.py
│   ├── schemas.py                # Pydantic models for API
│   └── events.py                 # Event type definitions
└── core/bot.py                   # MODIFY - add internal API

requirements/
├── base.txt                      # NEW - Common deps
├── bot.txt                       # NEW - Bot-specific
└── dashboard.txt                 # NEW - Dashboard-specific

docker/
├── docker-compose.yml            # MODIFY - add dashboard
├── docker-compose.bot-only.yml   # NEW - Headless mode
├── Dockerfile.dashboard          # NEW
└── Caddyfile                     # MODIFY - remove rate limit

tests/dashboard/                  # NEW
├── __init__.py
├── conftest.py
├── test_api/
│   ├── __init__.py
│   ├── test_status.py
│   ├── test_positions.py
│   └── test_control.py
├── test_websocket.py
├── test_auth.py
└── test_integration.py
```

2. **Create requirements files:**

`requirements/base.txt`:
```
# Common dependencies (bot + dashboard)
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
```

`requirements/bot.txt`:
```
# Bot-specific dependencies
-r base.txt
aiohttp>=3.9.0
web3>=6.0.0
solders>=0.20.0
solana>=0.30.0
tenacity>=8.0.0
pyyaml>=6.0
aiosqlite>=0.19.0
```

`requirements/dashboard.txt`:
```
# Dashboard-specific dependencies
-r base.txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
httpx>=0.25.0
jinja2>=3.1.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.0
python-multipart>=0.0.6
apscheduler>=3.10.0
msgpack>=1.0.0
structlog>=23.0.0
```

**Unit Tests:**
- [ ] `test_project_structure.py` - Verify all directories exist
- [ ] `test_requirements.py` - Verify all deps install without conflict

**Definition of Done:**
- [ ] All directories created with `__init__.py` files
- [ ] Requirements files created and installable
- [ ] No import errors when running `python -c "from src.dashboard import main"`

---

### Task 1.2: Shared Schemas Module
**Status:** `[ ]`  
**Priority:** Critical  
**Dependencies:** Task 1.1

**Context:** Bot and dashboard share Pydantic models. Extract serializable schemas to avoid duplication.

**Actions:**

1. **Create `src/shared/schemas.py`:**

```python
"""
Shared Pydantic models for bot-dashboard communication.
These models are serializable and used in both services.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

class BotState(str, Enum):
    STARTING = "starting"
    RECOVERING = "recovering"
    RUNNING = "running"
    DEGRADED = "degraded"
    SHUTDOWN = "shutdown"

class PauseScope(str, Enum):
    ALL = "all"
    ENTRY = "entry"
    EXIT = "exit"
    ASGARD = "asgard"
    HYPERLIQUID = "hyperliquid"

class PositionSummary(BaseModel):
    """Lightweight position for list views."""
    model_config = ConfigDict(json_encoders={Decimal: str})
    
    position_id: str
    asset: str
    status: str
    leverage: Decimal
    deployed_usd: Decimal
    long_value_usd: Decimal
    short_value_usd: Decimal
    delta: Decimal
    delta_ratio: Decimal
    asgard_hf: Decimal
    hyperliquid_mf: Decimal
    total_pnl_usd: Decimal
    funding_pnl_usd: Decimal
    opened_at: datetime
    hold_duration_hours: float

class PositionDetail(PositionSummary):
    """Full position details."""
    
    sizing: Dict[str, Decimal]
    asgard: Dict[str, Any]
    hyperliquid: Dict[str, Any]
    pnl: Dict[str, Decimal]
    risk: Dict[str, Any]

class BotStats(BaseModel):
    """Bot runtime statistics."""
    
    uptime_seconds: float
    uptime_formatted: str
    opportunities_found: int
    positions_opened: int
    positions_closed: int
    errors_count: int

class PauseState(BaseModel):
    """Current pause state."""
    
    paused: bool
    scope: PauseScope
    reason: Optional[str] = None
    paused_at: Optional[datetime] = None
    paused_by: Optional[str] = None
    active_breakers: List[str] = Field(default_factory=list)

class HealthStatus(BaseModel):
    """Combined health status."""
    
    status: str  # healthy, degraded, unhealthy
    timestamp: datetime
    version: str
    checks: Dict[str, Dict[str, Any]]
```

2. **Create `src/shared/events.py`:**

```python
"""
Event type definitions for WebSocket communication.
"""

from datetime import datetime
from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel

class SnapshotEvent(BaseModel):
    type: Literal["snapshot"] = "snapshot"
    seq: int
    timestamp: str
    data: Dict[str, Any]

class PositionUpdateEvent(BaseModel):
    type: Literal["position_update"] = "position_update"
    seq: int
    timestamp: str
    data: Dict[str, Any]

class PauseStateChangeEvent(BaseModel):
    type: Literal["pause_state_change"] = "pause_state_change"
    seq: int
    timestamp: str
    data: Dict[str, Any]

class TokenRefreshRequiredEvent(BaseModel):
    type: Literal["token_refresh_required"] = "token_refresh_required"
    timestamp: str
    refresh_url: str

class HeartbeatEvent(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"
    seq: int
    timestamp: str

class CatchUpEvent(BaseModel):
    type: Literal["catch_up"] = "catch_up"
    from_seq: int
    to_seq: int
    events: list
```

3. **Refactor bot to use shared schemas:**

Modify `src/core/bot.py`:
- Import schemas from `shared.schemas`
- Ensure `get_stats()`, `get_positions()` return schema-compatible objects
- Add `to_summary()` and `to_detail()` methods to position models if needed

**Unit Tests:**
- [ ] `test_schemas.py` - Test all schemas serialize/deserialize correctly
- [ ] `test_schemas_decimal.py` - Verify Decimal serialization as string
- [ ] `test_schemas_events.py` - Test event type validation

**Definition of Done:**
- [ ] All schemas defined with proper types
- [ ] Bot can import and use shared schemas
- [ ] Decimal fields serialize as strings (not floats)
- [ ] All unit tests pass

---

### Task 1.3: Bot Internal API
**Status:** `[ ]`  
**Priority:** Critical  
**Dependencies:** Task 1.2

**Context:** Bot exposes internal HTTP API on port 8000 for dashboard communication. This API is NOT exposed externally (Docker internal network only).

**Actions:**

1. **Create `src/core/internal_api.py`:**

```python
"""
Internal HTTP API for dashboard communication.
Runs on localhost:8000, NOT exposed externally.
"""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager

from src.shared.schemas import BotStats, PositionSummary, PositionDetail, PauseState
from src.core.pause_controller import PauseScope

security = HTTPBearer()
internal_app = FastAPI(title="Bot Internal API")

# Reference to bot instance (set during startup)
_bot_instance = None

def set_bot_instance(bot):
    global _bot_instance
    _bot_instance = bot

def get_bot():
    if _bot_instance is None:
        raise HTTPException(503, "Bot not initialized")
    return _bot_instance

def verify_internal_token(credentials: HTTPAuthorizationCredentials):
    """Verify the internal API token (different from admin_api_key)."""
    # For MVP, use same token as admin, but validate it
    from src.config.settings import get_settings
    settings = get_settings()
    
    if credentials.credentials != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token"
        )
    return credentials.credentials

@internal_app.get("/health")
async def health_check():
    """Basic health check - no auth required for load balancers."""
    if _bot_instance is None:
        return {"status": "starting"}
    
    return {
        "status": "healthy" if _bot_instance._running else "stopped",
        "state": _get_bot_state()
    }

def _get_bot_state() -> str:
    """Determine bot state for dashboard."""
    if _bot_instance is None:
        return "starting"
    if not _bot_instance._running:
        return "shutdown"
    if hasattr(_bot_instance, '_recovering') and _bot_instance._recovering:
        return "recovering"
    return "running"

@internal_app.get("/internal/stats", response_model=BotStats)
async def get_stats(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get bot statistics."""
    verify_internal_token(credentials)
    bot = get_bot()
    
    stats = bot.get_stats()
    return BotStats(
        uptime_seconds=stats.uptime_seconds,
        uptime_formatted=stats.uptime_formatted,
        opportunities_found=stats.opportunities_found,
        positions_opened=stats.positions_opened,
        positions_closed=stats.positions_closed,
        errors_count=len(stats.errors)
    )

@internal_app.get("/internal/positions")
async def get_positions(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all positions as dict."""
    verify_internal_token(credentials)
    bot = get_bot()
    
    positions = bot.get_positions()
    return {
        pos_id: _position_to_summary(pos).model_dump(mode="json")
        for pos_id, pos in positions.items()
    }

@internal_app.get("/internal/positions/{position_id}", response_model=PositionDetail)
async def get_position_detail(
    position_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get single position detail."""
    verify_internal_token(credentials)
    bot = get_bot()
    
    position = bot.get_positions().get(position_id)
    if not position:
        raise HTTPException(404, "Position not found")
    
    return _position_to_detail(position)

@internal_app.get("/internal/pause-state", response_model=PauseState)
async def get_pause_state(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get current pause state."""
    verify_internal_token(credentials)
    bot = get_bot()
    
    state = bot._pause_controller.get_pause_state()
    return PauseState(
        paused=state.paused,
        scope=PauseScope(state.scope.value),
        reason=state.reason,
        paused_at=state.paused_at,
        paused_by=state.paused_by,
        active_breakers=[b.value for b in state.active_breakers]
    )

@internal_app.post("/internal/control/pause")
async def pause_bot(
    request: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Pause bot operations."""
    verify_internal_token(credentials)
    bot = get_bot()
    
    # Bot validates api_key internally
    result = await bot.pause(
        api_key=request["api_key"],
        reason=request["reason"],
        scope=PauseScope(request.get("scope", "all"))
    )
    
    return {"success": result}

@internal_app.post("/internal/control/resume")
async def resume_bot(
    request: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Resume bot operations."""
    verify_internal_token(credentials)
    bot = get_bot()
    
    result = await bot.resume(api_key=request["api_key"])
    return {"success": result}

@internal_app.websocket("/internal/events")
async def events_websocket(websocket: WebSocket):
    """WebSocket for real-time events."""
    # TODO: Implement in Task 1.7
    await websocket.accept()
    # ... event subscription logic

def _position_to_summary(position) -> PositionSummary:
    """Convert CombinedPosition to PositionSummary."""
    return PositionSummary(
        position_id=position.position_id,
        asset=position.asgard.asset.value,
        status=position.status,
        leverage=position.asgard.leverage,
        deployed_usd=position.asgard.collateral_usd,
        long_value_usd=position.asgard.current_value_usd,
        short_value_usd=position.hyperliquid.size_usd,
        delta=position.delta,
        delta_ratio=position.delta_ratio,
        asgard_hf=position.asgard.current_health_factor,
        hyperliquid_mf=position.hyperliquid.margin_fraction,
        total_pnl_usd=position.total_pnl,
        funding_pnl_usd=position.net_funding_pnl,
        opened_at=position.created_at,
        hold_duration_hours=(datetime.utcnow() - position.created_at).total_seconds() / 3600
    )

def _position_to_detail(position) -> PositionDetail:
    """Convert CombinedPosition to PositionDetail."""
    summary = _position_to_summary(position)
    
    return PositionDetail(
        **summary.model_dump(),
        sizing={
            "deployed_usd": position.asgard.collateral_usd,
            "position_size_usd": position.asgard.position_size_usd,
            "collateral_usd": position.asgard.collateral_usd,
            "borrowed_usd": position.asgard.token_b_borrowed
        },
        asgard={
            "position_pda": position.asgard.position_pda,
            "collateral_usd": position.asgard.collateral_usd,
            "token_a_amount": position.asgard.token_a_amount,
            "entry_price": position.asgard.entry_price_token_a,
            "current_price": position.asgard.current_token_a_price,
            "current_health_factor": position.asgard.current_health_factor
        },
        hyperliquid={
            "size_sol": position.hyperliquid.size_sol,
            "entry_px": position.hyperliquid.entry_px,
            "mark_px": position.hyperliquid.mark_px,
            "leverage": position.hyperliquid.leverage,
            "margin_used": position.hyperliquid.margin_used,
            "margin_fraction": position.hyperliquid.margin_fraction
        },
        pnl={
            "long_pnl": position.asgard.pnl_usd,
            "short_pnl": position.hyperliquid.unrealized_pnl,
            "position_pnl": position.asgard.pnl_usd + position.hyperliquid.unrealized_pnl,
            "funding_pnl": position.net_funding_pnl,
            "total_pnl": position.total_pnl,
            "total_pnl_pct": position.total_pnl / position.asgard.collateral_usd if position.asgard.collateral_usd else 0
        },
        risk={
            "delta": position.delta,
            "delta_ratio": position.delta_ratio,
            "health_status": "healthy" if not position.is_at_risk else "at_risk",
            "distance_to_liquidation": min(
                position.asgard.current_health_factor,
                position.hyperliquid.distance_to_liquidation or 1
            )
        }
    )
```

2. **Modify bot to run internal API:**

Update `src/core/bot.py`:
```python
async def run(self):
    """Run bot with internal API server."""
    from src.core.internal_api import internal_app, set_bot_instance
    import uvicorn
    
    set_bot_instance(self)
    
    # Start internal API in background
    config = uvicorn.Config(
        internal_app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
    server = uvicorn.Server(config)
    api_task = asyncio.create_task(server.serve())
    
    # Run main bot loop
    try:
        self._running = True
        self._stats.start_time = datetime.utcnow()
        await self._recover_state()
        
        await asyncio.gather(
            self._monitor_loop(),
            self._scan_loop(),
        )
    finally:
        await api_task
```

**Unit Tests:**
- [ ] `test_internal_api_health.py` - Health endpoint returns correct status
- [ ] `test_internal_api_auth.py` - Invalid token returns 401
- [ ] `test_internal_api_positions.py` - Positions endpoint returns valid data
- [ ] `test_internal_api_control.py` - Pause/resume endpoints work

**Definition of Done:**
- [ ] Internal API runs on port 8000
- [ ] All endpoints require valid token
- [ ] Position serialization works correctly
- [ ] API returns proper error codes

---

### Task 1.4: BotBridge Implementation
**Status:** `[ ]`  
**Priority:** Critical  
**Dependencies:** Task 1.3

**Context:** BotBridge is the HTTP client that dashboard uses to communicate with bot. Implements stale-data caching.

**Actions:**

1. **Create `src/dashboard/bot_bridge.py`:**

```python
"""
Bridge between Dashboard and DeltaNeutralBot.
Implements stale-data caching for availability over consistency.
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
import httpx

from src.shared.schemas import BotStats, PositionSummary, PositionDetail, PauseState

logger = logging.getLogger(__name__)

class BotUnavailableError(Exception):
    """Raised when bot is not available."""
    pass

class BotBridge:
    """
    HTTP client for bot internal API with caching.
    
    Implements 5-second stale-data cache:
    - Returns fresh data if available
    - Returns cached data if bot slow (< 2s timeout)
    - Raises exception if no cached data available
    """
    
    def __init__(self, bot_api_url: str = "http://bot:8000", internal_token: str = None):
        self._api_url = bot_api_url
        self._internal_token = internal_token
        self._client = httpx.AsyncClient(
            base_url=bot_api_url,
            timeout=httpx.Timeout(5.0, connect=2.0)
        )
        
        # Cache storage
        self._cache: Dict[str, Any] = {}
        self._cache_timestamp: Dict[str, float] = {}
        self._cache_ttl = 5.0  # 5 seconds
        self._lock = asyncio.Lock()
        self._background_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start background cache refresh."""
        self._background_task = asyncio.create_task(self._background_refresh())
        logger.info("BotBridge started with background refresh")
    
    async def stop(self):
        """Stop background tasks."""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()
    
    async def _background_refresh(self):
        """Keep cache warm even without requests."""
        while True:
            await asyncio.sleep(5.0)
            try:
                await self.get_positions()
                await self.get_pause_state()
            except BotUnavailableError:
                logger.warning("Background refresh: bot unavailable")
            except Exception as e:
                logger.error(f"Background refresh failed: {e}")
    
    def _is_cache_fresh(self, key: str) -> bool:
        """Check if cache entry is still fresh."""
        if key not in self._cache_timestamp:
            return False
        return time.time() - self._cache_timestamp[key] < self._cache_ttl
    
    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached value if fresh."""
        if self._is_cache_fresh(key):
            return self._cache.get(key)
        return None
    
    def _set_cached(self, key: str, value: Any):
        """Cache a value."""
        self._cache[key] = value
        self._cache_timestamp[key] = time.time()
    
    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make authenticated request to bot API."""
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._internal_token}"
        
        try:
            response = await self._client.request(
                method, path, headers=headers, **kwargs
            )
            response.raise_for_status()
            return response
        except httpx.ConnectError as e:
            raise BotUnavailableError(f"Cannot connect to bot: {e}")
        except httpx.TimeoutException as e:
            raise BotUnavailableError(f"Bot request timeout: {e}")
    
    async def get_positions(self) -> Dict[str, PositionSummary]:
        """
        Get positions with caching.
        Returns stale data on timeout rather than fail.
        """
        cache_key = "positions"
        
        # Fast path: return cached data if fresh
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("Returning cached positions")
            return cached
        
        # Slow path: fetch from bot with short timeout
        try:
            async with asyncio.timeout(2.0):
                async with self._lock:
                    response = await self._request("GET", "/internal/positions")
                    data = response.json()
                    
                    positions = {
                        pos_id: PositionSummary(**pos_data)
                        for pos_id, pos_data in data.items()
                    }
                    
                    self._set_cached(cache_key, positions)
                    return positions
                    
        except asyncio.TimeoutError:
            logger.warning("Bot positions request timeout, using stale cache")
            cached = self._cache.get(cache_key)  # Use stale cache
            if cached is not None:
                return cached
            raise BotUnavailableError("No cached positions available")
        except BotUnavailableError:
            # Try to use stale cache
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.warning("Bot unavailable, returning stale positions")
                return cached
            raise
    
    async def get_position_detail(self, position_id: str) -> PositionDetail:
        """Get detailed position information."""
        cache_key = f"position_detail_{position_id}"
        
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        response = await self._request("GET", f"/internal/positions/{position_id}")
        detail = PositionDetail(**response.json())
        self._set_cached(cache_key, detail)
        return detail
    
    async def get_stats(self) -> BotStats:
        """Get bot statistics."""
        cache_key = "stats"
        
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        response = await self._request("GET", "/internal/stats")
        stats = BotStats(**response.json())
        self._set_cached(cache_key, stats)
        return stats
    
    async def get_pause_state(self) -> PauseState:
        """Get current pause state."""
        cache_key = "pause_state"
        
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        response = await self._request("GET", "/internal/pause-state")
        state = PauseState(**response.json())
        self._set_cached(cache_key, state)
        return state
    
    async def pause(self, api_key: str, reason: str, scope: str) -> bool:
        """Pause bot operations."""
        response = await self._request(
            "POST",
            "/internal/control/pause",
            json={"api_key": api_key, "reason": reason, "scope": scope}
        )
        return response.json()["success"]
    
    async def resume(self, api_key: str) -> bool:
        """Resume bot operations."""
        response = await self._request(
            "POST",
            "/internal/control/resume",
            json={"api_key": api_key}
        )
        return response.json()["success"]
    
    async def health_check(self) -> bool:
        """Check if bot is healthy."""
        try:
            response = await self._client.get("/health", timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False
    
    def invalidate_cache(self, key: str = None):
        """Invalidate cache entries."""
        if key:
            self._cache_timestamp.pop(key, None)
        else:
            self._cache_timestamp.clear()
```

**Unit Tests:**
- [ ] `test_bot_bridge_cache.py` - Cache returns fresh data
- [ ] `test_bot_bridge_stale_data.py` - Returns stale data on timeout
- [ ] `test_bot_bridge_no_cache.py` - Raises exception when no cache and bot down
- [ ] `test_bot_bridge_background_refresh.py` - Background task keeps cache warm

**Definition of Done:**
- [ ] BotBridge fetches data from bot API
- [ ] Cache returns data within 5 seconds
- [ ] Stale data returned on timeout (no hang)
- [ ] Background refresh works
- [ ] All unit tests pass

---

### Task 1.5: Dashboard FastAPI Application
**Status:** `[ ]`  
**Priority:** Critical  
**Dependencies:** Task 1.4

**Context:** Main dashboard application with FastAPI, including caching middleware and health checks.

**Actions:**

1. **Create `src/dashboard/config.py`:**

```python
"""Dashboard configuration."""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings

from src.config.settings import get_secret

class DashboardSettings(BaseSettings):
    """Dashboard-specific settings (NO trading secrets)."""
    
    # Server
    dashboard_host: str = Field(default="0.0.0.0", alias="DASHBOARD_HOST")
    dashboard_port: int = Field(default=8080, alias="DASHBOARD_PORT")
    
    # Bot connection
    bot_api_url: str = Field(default="http://bot:8000", alias="BOT_API_URL")
    
    # Auth secrets (dashboard-only, not trading keys)
    jwt_secret: str = Field(
        default_factory=lambda: get_secret("DASHBOARD_JWT_SECRET", "dashboard_jwt.txt") or "dev-secret-change-in-production"
    )
    session_secret: str = Field(
        default_factory=lambda: get_secret("DASHBOARD_SESSION_SECRET", "dashboard_session.txt") or "dev-session-change-in-production"
    )
    
    # Bot admin key reference (for proxying control requests)
    bot_admin_key: str = Field(
        default_factory=lambda: get_secret("ADMIN_API_KEY", "admin_api_key.txt") or ""
    )
    
    # Alert channels (optional)
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")
    alert_webhook_url: Optional[str] = Field(default=None, alias="ALERT_WEBHOOK_URL")
    discord_webhook_url: Optional[str] = Field(default=None, alias="DISCORD_WEBHOOK_URL")
    
    # Cache settings
    cache_ttl: float = Field(default=5.0, alias="CACHE_TTL")
    
    class Config:
        env_file = ".env"

# Singleton instance
_settings: Optional[DashboardSettings] = None

def get_dashboard_settings() -> DashboardSettings:
    global _settings
    if _settings is None:
        _settings = DashboardSettings()
    return _settings
```

2. **Create `src/dashboard/main.py`:**

```python
"""Dashboard FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.dashboard.config import get_dashboard_settings
from src.dashboard.bot_bridge import BotBridge
from src.dashboard.api import status, positions, control, config as config_api
from src.dashboard.middleware.logging import logging_middleware

logger = logging.getLogger(__name__)

# Global bot bridge instance
bot_bridge: BotBridge = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global bot_bridge
    
    # Startup
    settings = get_dashboard_settings()
    bot_bridge = BotBridge(
        bot_api_url=settings.bot_api_url,
        internal_token=settings.bot_admin_key
    )
    await bot_bridge.start()
    
    logger.info(f"Dashboard started, connected to bot at {settings.bot_api_url}")
    
    yield
    
    # Shutdown
    await bot_bridge.stop()
    logger.info("Dashboard shutdown complete")

app = FastAPI(
    title="Delta Neutral Bot Dashboard",
    description="Control center for Delta Neutral Funding Rate Arbitrage Bot",
    version="1.0.0",
    lifespan=lifespan
)

# Middleware
app.middleware("http")(logging_middleware)

# CORS (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to dashboard domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="src/dashboard/static"), name="static")

# API routes
app.include_router(status.router, prefix="/api/v1", tags=["status"])
app.include_router(positions.router, prefix="/api/v1", tags=["positions"])
app.include_router(control.router, prefix="/api/v1", tags=["control"])
app.include_router(config_api.router, prefix="/api/v1", tags=["config"])

@app.get("/")
async def root():
    """Redirect to dashboard."""
    return {"message": "Delta Neutral Bot Dashboard", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    settings = get_dashboard_settings()
    uvicorn.run(
        "src.dashboard.main:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        reload=True
    )
```

3. **Create `src/dashboard/middleware/logging.py`:**

```python
"""Logging middleware with correlation IDs."""

import time
import uuid
import structlog
from fastapi import Request

logger = structlog.get_logger()

async def logging_middleware(request: Request, call_next):
    """Add correlation ID and log request."""
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else None
    )
    
    start_time = time.time()
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        
        logger.info(
            "Request completed",
            status_code=response.status_code,
            duration_ms=round(process_time * 1000, 2)
        )
        
        response.headers["X-Correlation-ID"] = correlation_id
        return response
        
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            "Request failed",
            error=str(e),
            duration_ms=round(process_time * 1000, 2)
        )
        raise
```

4. **Create `src/dashboard/api/status.py`:**

```python
"""Status and health endpoints."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from src.dashboard.main import bot_bridge
from src.shared.schemas import HealthStatus, BotStats, PauseState

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Comprehensive health check including dependencies.
    Used by Docker healthcheck and load balancers.
    """
    checks = {
        "dashboard": {"status": "healthy", "response_time_ms": 0},
        "bot_api": {"status": "unknown", "response_time_ms": 0},
    }
    
    overall_status = "healthy"
    
    # Check bot API
    import time
    start = time.time()
    bot_healthy = await bot_bridge.health_check()
    checks["bot_api"]["response_time_ms"] = int((time.time() - start) * 1000)
    checks["bot_api"]["status"] = "healthy" if bot_healthy else "degraded"
    
    if not bot_healthy:
        overall_status = "degraded"
    
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

@router.get("/status")
async def get_status():
    """Get detailed bot status."""
    try:
        pause_state = await bot_bridge.get_pause_state()
        stats = await bot_bridge.get_stats()
        bot_healthy = await bot_bridge.health_check()
        
        return {
            "bot": {
                "healthy": bot_healthy,
                "state": "running" if bot_healthy else "unavailable"
            },
            "pause_state": pause_state.model_dump(),
            "stats": stats.model_dump(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(503, f"Bot unavailable: {e}")

@router.get("/stats", response_model=BotStats)
async def get_stats():
    """Get bot statistics."""
    return await bot_bridge.get_stats()

@router.get("/pause-state", response_model=PauseState)
async def get_pause_state():
    """Get current pause state."""
    return await bot_bridge.get_pause_state()
```

**Unit Tests:**
- [ ] `test_dashboard_startup.py` - App starts and connects to bot
- [ ] `test_health_check.py` - Returns correct status codes
- [ ] `test_status_endpoint.py` - Returns bot status when available
- [ ] `test_status_bot_down.py` - Returns 503 when bot down

**Definition of Done:**
- [ ] FastAPI app starts on port 8080
- [ ] Health endpoint works
- [ ] BotBridge initialized on startup
- [ ] Graceful shutdown closes connections
- [ ] All unit tests pass

---

### Task 1.6: Position Endpoints
**Status:** `[ ]`  
**Priority:** High  
**Dependencies:** Task 1.5

**Actions:**

1. **Create `src/dashboard/api/positions.py`:**

```python
"""Position API endpoints."""

from typing import Dict
from fastapi import APIRouter, HTTPException

from src.dashboard.main import bot_bridge
from src.shared.schemas import PositionSummary, PositionDetail

router = APIRouter()

@router.get("/positions")
async def get_positions() -> Dict[str, list]:
    """List all positions with summary."""
    try:
        positions = await bot_bridge.get_positions()
        
        # Calculate summary
        total_pnl = sum(p.total_pnl_usd for p in positions.values())
        total_deployed = sum(p.deployed_usd for p in positions.values())
        
        return {
            "positions": [p.model_dump() for p in positions.values()],
            "summary": {
                "total_positions": len(positions),
                "open_positions": sum(1 for p in positions.values() if p.status == "open"),
                "closed_positions": sum(1 for p in positions.values() if p.status == "closed"),
                "total_pnl_usd": float(total_pnl),
                "total_deployed_usd": float(total_deployed)
            },
            "cached_at": bot_bridge._cache_timestamp.get("positions")
        }
    except Exception as e:
        raise HTTPException(503, f"Failed to fetch positions: {e}")

@router.get("/positions/{position_id}", response_model=PositionDetail)
async def get_position_detail(position_id: str):
    """Get detailed position information."""
    try:
        detail = await bot_bridge.get_position_detail(position_id)
        return detail
    except Exception as e:
        raise HTTPException(404, f"Position not found: {e}")
```

**Unit Tests:**
- [ ] `test_get_positions.py` - Returns position list
- [ ] `test_get_position_detail.py` - Returns detailed position
- [ ] `test_position_not_found.py` - Returns 404 for unknown position

**Definition of Done:**
- [ ] Position list endpoint works
- [ ] Position detail endpoint works
- [ ] Summary calculations correct
- [ ] All unit tests pass

---

### Task 1.7: Control Endpoints
**Status:** `[ ]`  
**Priority:** High  
**Dependencies:** Task 1.5

**Context:** Control endpoints for pause/resume. Phase 1 uses API key auth only (JWT in Phase 4).

**Actions:**

1. **Create `src/dashboard/api/control.py`:**

```python
"""Control endpoints for pause/resume/emergency."""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from src.dashboard.main import bot_bridge
from src.dashboard.config import get_dashboard_settings

router = APIRouter()

class PauseRequest(BaseModel):
    reason: str
    scope: str = "all"  # all, entry, exit, asgard, hyperliquid
    api_key: str

class ResumeRequest(BaseModel):
    api_key: str

@router.post("/control/pause")
async def pause_bot(request: PauseRequest):
    """
    Pause bot operations.
    Requires admin API key.
    """
    settings = get_dashboard_settings()
    
    # Validate API key
    if request.api_key != settings.bot_admin_key:
        raise HTTPException(401, "Invalid API key")
    
    try:
        result = await bot_bridge.pause(
            api_key=request.api_key,
            reason=request.reason,
            scope=request.scope
        )
        
        # Invalidate cache to reflect new state
        bot_bridge.invalidate_cache("pause_state")
        
        return {
            "success": result,
            "paused_at": datetime.utcnow().isoformat(),
            "scope": request.scope,
            "reason": request.reason
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to pause bot: {e}")

@router.post("/control/resume")
async def resume_bot(request: ResumeRequest):
    """
    Resume bot operations.
    Requires admin API key.
    """
    settings = get_dashboard_settings()
    
    if request.api_key != settings.bot_admin_key:
        raise HTTPException(401, "Invalid API key")
    
    try:
        result = await bot_bridge.resume(api_key=request.api_key)
        
        bot_bridge.invalidate_cache("pause_state")
        
        return {
            "success": result,
            "resumed_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to resume bot: {e}")

@router.post("/control/emergency-stop")
async def emergency_stop(request: ResumeRequest):
    """
    Emergency stop - pause all operations immediately.
    """
    # Same as pause with scope=all, but can add additional actions later
    return await pause_bot(PauseRequest(
        reason="EMERGENCY STOP triggered via dashboard",
        scope="all",
        api_key=request.api_key
    ))
```

**Unit Tests:**
- [ ] `test_pause_bot.py` - Pause with valid key works
- [ ] `test_pause_invalid_key.py` - Invalid key returns 401
- [ ] `test_resume_bot.py` - Resume with valid key works
- [ ] `test_emergency_stop.py` - Emergency stop pauses all

**Definition of Done:**
- [ ] Pause endpoint works with valid API key
- [ ] Resume endpoint works with valid API key
- [ ] Invalid API key returns 401
- [ ] Cache invalidated after state change
- [ ] All unit tests pass

---

### Task 1.8: Basic HTML UI
**Status:** `[ ]`  
**Priority:** High  
**Dependencies:** Task 1.6, 1.7

**Context:** Minimal HTML UI for MVP. HTMX + Alpine.js + Tailwind CSS. No frameworks.

**Actions:**

1. **Create `src/dashboard/templates/base.html`:**

```html
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Delta Neutral Bot{% endblock %}</title>
    
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        primary: '#3b82f6',
                        success: '#22c55e',
                        danger: '#ef4444',
                        warning: '#f59e0b',
                    }
                }
            }
        }
    </script>
    
    <!-- HTMX -->
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    
    <!-- Alpine.js -->
    <script defer src="https://unpkg.com/alpinejs@3.13.3/dist/cdn.min.js"></script>
    
    {% block head %}{% endblock %}
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen">
    <!-- Navigation -->
    <nav class="bg-slate-800 border-b border-slate-700">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex items-center justify-between h-16">
                <div class="flex items-center">
                    <a href="/" class="text-xl font-bold text-primary">Delta Neutral Bot</a>
                    <div class="ml-10 flex items-baseline space-x-4">
                        <a href="/" class="px-3 py-2 rounded-md text-sm font-medium hover:bg-slate-700">Dashboard</a>
                        <a href="/positions" class="px-3 py-2 rounded-md text-sm font-medium hover:bg-slate-700">Positions</a>
                    </div>
                </div>
                <div class="flex items-center space-x-4">
                    <span id="connection-status" class="flex items-center">
                        <span class="h-2 w-2 rounded-full bg-success mr-2"></span>
                        Connected
                    </span>
                </div>
            </div>
        </div>
    </nav>
    
    <!-- Main content -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {% block content %}{% endblock %}
    </main>
    
    {% block scripts %}{% endblock %}
</body>
</html>
```

2. **Create `src/dashboard/templates/dashboard.html`:**

```html
{% extends "base.html" %}

{% block content %}
<div x-data="dashboard()" x-init="init()">
    <!-- Status Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <!-- Uptime -->
        <div class="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h3 class="text-sm font-medium text-slate-400">Uptime</h3>
            <p class="mt-2 text-2xl font-bold" x-text="stats.uptime_formatted || '--:--:--'"></p>
        </div>
        
        <!-- Positions -->
        <div class="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h3 class="text-sm font-medium text-slate-400">Positions</h3>
            <p class="mt-2 text-2xl font-bold" x-text="summary.open_positions || 0"></p>
        </div>
        
        <!-- PnL -->
        <div class="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h3 class="text-sm font-medium text-slate-400">Total PnL</h3>
            <p class="mt-2 text-2xl font-bold" 
               :class="summary.total_pnl_usd >= 0 ? 'text-success' : 'text-danger'"
               x-text="'$' + (summary.total_pnl_usd || 0).toFixed(2)"></p>
        </div>
        
        <!-- Status -->
        <div class="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h3 class="text-sm font-medium text-slate-400">Status</h3>
            <div class="mt-2 flex items-center">
                <span class="h-3 w-3 rounded-full mr-2"
                      :class="pause_state.paused ? 'bg-danger' : 'bg-success'"></span>
                <span class="text-lg font-bold" x-text="pause_state.paused ? 'PAUSED' : 'RUNNING'"></span>
            </div>
        </div>
    </div>
    
    <!-- Control Panel -->
    <div class="bg-slate-800 rounded-lg p-6 border border-slate-700 mb-8">
        <h2 class="text-lg font-medium mb-4">Control Panel</h2>
        <div class="flex space-x-4">
            <button @click="pause('entry')" 
                    :disabled="pause_state.paused"
                    class="px-4 py-2 bg-warning text-slate-900 rounded hover:bg-warning/80 disabled:opacity-50">
                Pause Entry
            </button>
            <button @click="pause('all')"
                    :disabled="pause_state.paused"
                    class="px-4 py-2 bg-danger text-white rounded hover:bg-danger/80 disabled:opacity-50">
                Pause All
            </button>
            <button @click="resume()"
                    :disabled="!pause_state.paused"
                    class="px-4 py-2 bg-success text-slate-900 rounded hover:bg-success/80 disabled:opacity-50">
                Resume
            </button>
        </div>
        <p x-show="pause_state.reason" class="mt-4 text-sm text-slate-400" x-text="'Reason: ' + pause_state.reason"></p>
    </div>
    
    <!-- Positions List -->
    <div class="bg-slate-800 rounded-lg border border-slate-700">
        <div class="px-6 py-4 border-b border-slate-700">
            <h2 class="text-lg font-medium">Active Positions</h2>
        </div>
        <div class="divide-y divide-slate-700">
            <template x-for="position in positions" :key="position.position_id">
                <div class="px-6 py-4 flex items-center justify-between hover:bg-slate-700/50">
                    <div>
                        <span class="font-medium" x-text="position.asset"></span>
                        <span class="ml-2 text-sm text-slate-400" x-text="position.leverage + 'x'"></span>
                    </div>
                    <div class="flex items-center space-x-6">
                        <div class="text-right">
                            <p class="text-sm text-slate-400">PnL</p>
                            <p class="font-medium" 
                               :class="position.total_pnl_usd >= 0 ? 'text-success' : 'text-danger'"
                               x-text="'$' + position.total_pnl_usd.toFixed(2)"></p>
                        </div>
                        <div class="text-right">
                            <p class="text-sm text-slate-400">Health</p>
                            <p class="font-medium" x-text="(position.asgard_hf * 100).toFixed(1) + '%'"></p>
                        </div>
                    </div>
                </div>
            </template>
        </div>
    </div>
</div>

<script>
function dashboard() {
    return {
        positions: [],
        summary: {},
        stats: {},
        pause_state: {},
        apiKey: localStorage.getItem('api_key') || '',
        
        init() {
            this.fetchData();
            // Poll every 5 seconds
            setInterval(() => this.fetchData(), 5000);
        },
        
        async fetchData() {
            try {
                const [positionsRes, statusRes] = await Promise.all([
                    fetch('/api/v1/positions'),
                    fetch('/api/v1/status')
                ]);
                
                if (positionsRes.ok) {
                    const data = await positionsRes.json();
                    this.positions = data.positions;
                    this.summary = data.summary;
                }
                
                if (statusRes.ok) {
                    const data = await statusRes.json();
                    this.stats = data.stats;
                    this.pause_state = data.pause_state;
                }
            } catch (e) {
                console.error('Failed to fetch data:', e);
            }
        },
        
        async pause(scope) {
            if (!this.apiKey) {
                this.apiKey = prompt('Enter admin API key:');
                localStorage.setItem('api_key', this.apiKey);
            }
            
            const reason = prompt('Reason for pause:');
            if (!reason) return;
            
            try {
                const res = await fetch('/api/v1/control/pause', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({api_key: this.apiKey, reason, scope})
                });
                
                if (res.ok) {
                    this.fetchData();
                } else {
                    alert('Failed to pause: ' + await res.text());
                }
            } catch (e) {
                alert('Error: ' + e);
            }
        },
        
        async resume() {
            if (!this.apiKey) {
                this.apiKey = prompt('Enter admin API key:');
                localStorage.setItem('api_key', this.apiKey);
            }
            
            try {
                const res = await fetch('/api/v1/control/resume', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({api_key: this.apiKey})
                });
                
                if (res.ok) {
                    this.fetchData();
                } else {
                    alert('Failed to resume: ' + await res.text());
                }
            } catch (e) {
                alert('Error: ' + e);
            }
        }
    }
}
</script>
{% endblock %}
```

3. **Update `src/dashboard/main.py` to add template routes:**

```python
from fastapi import Request
from fastapi.templating import Jinja2Templates

# Add after app creation
templates = Jinja2Templates(directory="src/dashboard/templates")

@app.get("/")
async def dashboard_page(request: Request):
    """Render main dashboard page."""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/positions")
async def positions_page(request: Request):
    """Render positions page."""
    return templates.TemplateResponse("positions.html", {"request": request})
```

**Unit Tests:**
- [ ] `test_dashboard_page.py` - Page renders without error
- [ ] `test_dashboard_data.py` - Data displayed correctly
- [ ] `test_control_buttons.py` - Buttons trigger correct actions

**Definition of Done:**
- [ ] Dashboard page loads at `/`
- [ ] Status cards display correctly
- [ ] Control buttons work (pause/resume)
- [ ] Position list displays
- [ ] Auto-refreshes every 5 seconds
- [ ] Dark mode by default

---

### Task 1.9: Docker Configuration
**Status:** `[ ]`  
**Priority:** High  
**Dependencies:** Task 1.8

**Actions:**

1. **Create `docker/Dockerfile.dashboard`:**

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DASHBOARD_ENV=production

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r dashboard && useradd -r -g dashboard -s /bin/false dashboard

# Install Python deps
COPY requirements/base.txt /tmp/base.txt
COPY requirements/dashboard.txt /tmp/dashboard.txt
RUN pip install --no-cache-dir -r /tmp/dashboard.txt

WORKDIR /app

# Copy code
COPY src/dashboard/ ./src/dashboard/
COPY src/shared/ ./src/shared/
COPY src/config/ ./src/config/

# Create data directory
RUN mkdir -p /app/data && chown -R dashboard:dashboard /app

USER dashboard

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f "http://localhost:8080/api/v1/health" --max-time 4 || exit 1

CMD ["uvicorn", "src.dashboard.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

2. **Update `docker/docker-compose.yml`:**

```yaml
services:
  # Existing bot service...
  bot:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    expose:
      - "8000"  # Internal API only
    volumes:
      - bot-data:/app/data
    networks:
      - bot-network

  # NEW: Dashboard service
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
      - BOT_API_URL=http://bot:8000
      # Secrets from files
      - DASHBOARD_JWT_SECRET=${DASHBOARD_JWT_SECRET}
      - ADMIN_API_KEY=${ADMIN_API_KEY}
    
    volumes:
      - bot-data:/app/data:ro  # Read-only access to bot state
    
    ports:
      - "8080:8080"
    
    networks:
      - bot-network
    
    depends_on:
      - bot
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/api/v1/health", "--max-time", "4"]
      interval: 30s
      timeout: 5s
      retries: 3

  # Proxy service
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
  bot-data:
    driver: local
  caddy-data:
    driver: local
  caddy-config:
    driver: local

networks:
  bot-network:
    driver: bridge
```

3. **Update `docker/Caddyfile`:**

```caddyfile
dashboard.yourdomain.com {
    tls admin@yourdomain.com
    
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        X-XSS-Protection "1; mode=block"
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }
    
    @websockets {
        header Connection *Upgrade*
        header Upgrade websocket
    }
    reverse_proxy @websockets dashboard:8080
    
    reverse_proxy dashboard:8080
}
```

**Integration Tests:**
- [ ] `test_docker_build.py` - Dashboard image builds
- [ ] `test_docker_compose.py` - Services start and connect
- [ ] `test_dashboard_bot_communication.py` - Dashboard can reach bot

**Definition of Done:**
- [ ] Dashboard container builds
- [ ] Docker compose starts all services
- [ ] Dashboard accessible via Caddy proxy
- [ ] Health checks pass
- [ ] Dashboard can communicate with bot

---

### Phase 1 Success Criteria

- [ ] Dashboard accessible at http://localhost:8080
- [ ] Real-time position monitoring works (5s polling)
- [ ] Can pause/resume bot operations via UI
- [ ] Survives bot restarts gracefully (shows cached data)
- [ ] All Phase 1 unit tests passing (target: 50+ tests)
- [ ] Docker compose deployment works

---

## Phase 2: Enhanced UX - Visualization

**Goal:** Rich data presentation and mobile support

**Prerequisites:** Phase 1 complete

---

### Task 2.1: PnL Charts
**Status:** `[ ]`  
**Priority:** High

**Context:** Interactive Chart.js visualizations for PnL history.

**Actions:**
1. Add Chart.js to base template
2. Create `/api/v1/history/pnl` endpoint with auto-downsampling
3. Create chart component with 24h/7d/30d/90d tabs
4. Handle UTC to local time conversion

**Unit Tests:**
- [ ] Chart renders with data
- [ ] Time range switching works
- [ ] Downsampling returns correct resolution

---

### Task 2.2: Position Detail Page
**Status:** `[ ]`  
**Priority:** High

**Context:** Individual position drill-down with full lifecycle.

**Actions:**
1. Create `/positions/{id}` route
2. Display position legs (Asgard + Hyperliquid)
3. Show entry/exit prices
4. Display funding payment history

**Unit Tests:**
- [ ] Detail page loads
- [ ] All position fields displayed
- [ ] Invalid position returns 404

---

### Task 2.3: Mobile Responsive UI
**Status:** `[ ]`  
**Priority:** High

**Context:** Vertical accordion layout for mobile.

**Actions:**
1. Add responsive breakpoints to Tailwind config
2. Convert horizontal cards to vertical stack on mobile
3. Make position list collapsible
4. Ensure touch targets > 44px

**Unit Tests:**
- [ ] Layout adjusts at 768px breakpoint
- [ ] All elements accessible on mobile
- [ ] Charts pan/zoom work on touch

---

### Task 2.4: Dark Mode Toggle
**Status:** `[ ]`  
**Priority:** Medium

**Context:** Toggle between light/dark themes.

**Actions:**
1. Add theme toggle button to nav
2. Persist preference in localStorage
3. Toggle `dark` class on `<html>` element

**Unit Tests:**
- [ ] Toggle switches theme
- [ ] Preference persists across reloads

---

## Phase 3: Alerting - Notifications

**Goal:** Proactive monitoring and external notifications

**Prerequisites:** Phase 2 complete

---

### Task 3.1: Alert Engine
**Status:** `[ ]`  
**Priority:** Critical

**Context:** Event evaluation with progressive severity.

**Actions:**
1. Create `src/dashboard/alerts/engine.py`
2. Implement per-metric throttling
3. Progressive severity for health factors
4. Alert history persistence

**Unit Tests:**
- [ ] Alert triggers when threshold crossed
- [ ] Throttling prevents spam
- [ ] Progressive escalation works

---

### Task 3.2: Telegram Bot
**Status:** `[ ]`  
**Priority:** High

**Context:** Bot commands and push notifications.

**Actions:**
1. Create Telegram bot handler
2. Implement commands: /status, /pause, /resume
3. Add per-user rate limiting (5 commands/min)
4. Send push notifications for critical alerts

**Unit Tests:**
- [ ] Commands respond correctly
- [ ] Rate limiting enforced
- [ ] Notifications sent on alerts

---

### Task 3.3: Webhook Channel
**Status:** `[ ]`  
**Priority:** High

**Context:** Generic HTTP POST for Slack/PagerDuty integration.

**Actions:**
1. Create webhook channel handler
2. Support custom headers
3. Retry with exponential backoff
4. Circuit breaker on repeated failures

**Unit Tests:**
- [ ] Webhook delivers payload
- [ ] Retries on failure
- [ ] Circuit breaker opens after 5 failures

---

## Phase 4: Production - Security & Scale

**Goal:** Enterprise-ready deployment and access control

**Prerequisites:** Phase 3 complete

---

### Task 4.1: JWT Authentication
**Status:** `[ ]`  
**Priority:** Critical

**Context:** Replace API key auth in browser with JWT sessions.

**Actions:**
1. Create login page
2. Implement JWT token generation
3. Add refresh token mechanism
4. Secure token storage

**Unit Tests:**
- [ ] Login generates valid JWT
- [ ] Protected endpoints reject invalid tokens
- [ ] Token refresh works

---

### Task 4.2: User Management
**Status:** `[ ]`  
**Priority:** High

**Context:** Multi-user with role-based access.

**Actions:**
1. Create user database table
2. Password hashing with bcrypt
3. Role-based middleware
4. User admin UI

**Unit Tests:**
- [ ] User creation works
- [ ] Passwords hashed correctly
- [ ] Roles enforced on endpoints

---

### Task 4.3: Rate Limiting
**Status:** `[ ]`  
**Priority:** High

**Context:** Application-level per-user rate limiting.

**Actions:**
1. Create rate limiting middleware
2. Different limits per role
3. Redis backend for distributed rate limiting (future)
4. Rate limit headers in responses

**Unit Tests:**
- [ ] Rate limits enforced
- [ ] Different limits for different roles
- [ ] Headers present in responses

---

## Appendix A: Running the Dashboard

### Development Mode

```bash
# Terminal 1: Start bot
python -m src.core.bot

# Terminal 2: Start dashboard
cd src/dashboard
uvicorn main:app --reload --port 8080

# Open http://localhost:8080
```

### Docker Mode

```bash
# Build and start all services
docker-compose up --build

# Dashboard: http://localhost:8080
# API docs: http://localhost:8080/docs
```

### Testing

```bash
# Run dashboard tests only
pytest tests/dashboard/ -v

# Run with coverage
pytest tests/dashboard/ --cov=src.dashboard --cov-report=html
```

---

## Appendix B: Key Files Reference

| File | Purpose |
|------|---------|
| `spec-dashboard.md` | Full technical specification |
| `dashboard_questions.md` | Q&A with architectural decisions |
| `src/dashboard/main.py` | FastAPI application entry |
| `src/dashboard/bot_bridge.py` | HTTP client to bot with caching |
| `src/shared/schemas.py` | Shared Pydantic models |
| `src/core/internal_api.py` | Bot's internal HTTP API |
| `docker/docker-compose.yml` | Full deployment config |

---

*Document Version: 1.0*  
*Last Updated: 2026-02-05*  
*Target: Context transfer for future agents*
