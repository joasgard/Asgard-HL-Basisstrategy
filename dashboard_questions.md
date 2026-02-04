# Dashboard Deep-Dive Questions & Recommendations

This document contains 23 non-obvious questions about the dashboard architecture, UX, security, and operations - along with recommended approaches based on best practices for financial trading systems.

**How to use this:** Review each recommendation and mark changes where the approach doesn't fit your operational needs. Questions are organized by category for easier review.

---

## Architecture & Integration

### Q1: BotBridge uses `asyncio.Lock()` - serializes operations and blocks on slow RPC calls

**Question:** The current design would block all dashboard requests if `get_positions()` takes 500ms. How should we handle this?

**Recommendation:**
```python
# Use stale-data cache with background refresh
class BotBridge:
    def __init__(self):
        self._cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 5.0  # 5 seconds max stale data
        self._lock = asyncio.Lock()
        self._background_task = None
    
    async def get_positions(self) -> Dict[str, Any]:
        # Fast path: return cache if fresh
        if time.time() - self._cache_timestamp < self._cache_ttl:
            return self._cache.get("positions", {})
        
        # Slow path: refresh with timeout
        try:
            async with asyncio.timeout(2.0):  # Max 2s wait
                async with self._lock:
                    positions = await self._fetch_from_bot()
                    self._cache["positions"] = positions
                    self._cache_timestamp = time.time()
                    return positions
        except asyncio.TimeoutError:
            # Return stale data rather than hang
            logger.warning("Bot response timeout, returning cached positions")
            return self._cache.get("positions", {})
    
    async def start_background_refresh(self):
        """Keep cache warm even when no requests coming in."""
        while True:
            await asyncio.sleep(5.0)
            try:
                await self.get_positions()
            except Exception as e:
                logger.error(f"Background refresh failed: {e}")
```

**Rationale:**
- Trading dashboards should prioritize availability over strict consistency
- 5-second stale data is acceptable for UI display (actual trading decisions happen in bot)
- Background refresh keeps cache warm for immediate UI response
- Timeout prevents cascading failures

**Trade-off accepting:** Brief inconsistency between dashboard and ground truth; acceptable for monitoring UI.

---

### Q2: Docker-compose shows separate service, but spec mentions "shared memory" - which is it?

**Question:** The architecture diagram and docker-compose conflict. Which deployment model?

**Recommendation:**

**Definitive Answer: Separate containers with HTTP API**

```yaml
# docker-compose.yml (final)
services:
  bot:
    build:
      context: .
      dockerfile: docker/Dockerfile
    expose:
      - "8000"  # Internal API only, not published to host
    volumes:
      - bot-data:/app/data
    networks:
      - bot-network

  dashboard:
    build:
      context: .
      dockerfile: docker/Dockerfile.dashboard
    ports:
      - "8080:8080"  # Only dashboard exposed externally
    environment:
      - BOT_API_URL=http://bot:8000
    volumes:
      - bot-data:/app/data:ro  # Read-only access to state
    networks:
      - bot-network
    depends_on:
      - bot
```

**Bot internal API (port 8000):**
```python
# src/core/bot_internal_api.py
# Runs on localhost:8000, NOT exposed externally

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer

internal_app = FastAPI()
security = HTTPBearer()

@internal_app.get("/internal/positions")
async def get_positions(credentials=Depends(security)):
    """Only accessible within Docker network."""
    verify_internal_token(credentials.credentials)
    return bot.get_positions()

@internal_app.post("/internal/control/pause")
async def pause(request: PauseRequest):
    """Dashboard proxies authenticated requests here."""
    return await bot.pause(request.api_key, request.reason, request.scope)
```

**Why not shared memory:**
- Crash isolation (dashboard OOM doesn't kill bot)
- Independent scaling
- Clear API contract forces better design
- Easier to test dashboard against mock bot

---

### Q3: Bot callbacks execute in bot's event loop - blocking WebSocket broadcast stalls bot

**Question:** If `_on_position_opened` hangs, what happens to the bot's main loop?

**Recommendation:**

**Use fire-and-forget with circuit breaker:**

```python
class BotBridge:
    def __init__(self):
        self._event_queue = asyncio.Queue(maxsize=1000)
        self._circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        self._forwarding_task = None
    
    def register_callbacks(self):
        """Register non-blocking callbacks that just enqueue."""
        self._bot.add_position_opened_callback(
            lambda pos: self._enqueue_event("position_opened", pos)
        )
        # Start background forwarding task
        self._forwarding_task = asyncio.create_task(self._forward_events())
    
    def _enqueue_event(self, event_type: str, data):
        """Non-blocking enqueue with drop-on-full."""
        try:
            self._event_queue.put_nowait({
                "type": event_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            })
        except asyncio.QueueFull:
            logger.warning(f"Event queue full, dropping {event_type}")
    
    async def _forward_events(self):
        """Background task forwards events to WebSocket clients."""
        while True:
            event = await self._event_queue.get()
            
            if not self._circuit_breaker.allow_request():
                continue  # Skip during circuit breaker open
            
            try:
                await asyncio.wait_for(
                    self._broadcast_to_websockets(event),
                    timeout=1.0
                )
                self._circuit_breaker.record_success()
            except asyncio.TimeoutError:
                self._circuit_breaker.record_failure()
                logger.warning("WebSocket broadcast timeout")
            except Exception as e:
                self._circuit_breaker.record_failure()
                logger.error(f"Broadcast failed: {e}")
```

**Key protections:**
1. **Queue decouples** bot from WebSocket delays
2. **Drop-on-full** prevents memory explosion during outages
3. **Circuit breaker** stops trying after repeated failures
4. **Background task** isolates slow I/O from bot callback
5. **1-second timeout** per broadcast prevents indefinite blocking

**Monitoring:** Alert when queue depth > 100 or circuit breaker opens.

---

## Data Consistency & State Management

### Q4: WebSocket consistency model - client connects mid-position, misses "opened" event

**Question:** What's the consistency model for new WebSocket connections?

**Recommendation:**

**Snapshot + delta pattern:**

```python
class WebSocketManager:
    async def handle_connection(self, websocket: WebSocket):
        await websocket.accept()
        
        # 1. Send full snapshot immediately on connect
        snapshot = {
            "type": "snapshot",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "positions": await self._bridge.get_positions(),
                "pause_state": await self._bridge.get_pause_state(),
                "stats": await self._bridge.get_stats()
            }
        }
        await websocket.send_json(snapshot)
        
        # 2. Subscribe to delta updates
        self._add_subscriber(websocket)
        
        try:
            while True:
                # Keep connection alive, handle client pings
                data = await websocket.receive_json()
                if data.get("action") == "ping":
                    await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            self._remove_subscriber(websocket)
```

**Client-side handling:**
```javascript
// Client must handle snapshot then deltas
let state = null;

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    
    if (msg.type === "snapshot") {
        // Replace entire state
        state = msg.data;
        renderDashboard(state);
    } else if (msg.type === "position_update") {
        // Apply delta
        state.positions[msg.data.position_id] = msg.data;
        updatePositionCard(msg.data);
    }
};
```

**Alternative for very large state:** Send snapshot compressed (gzip) or paginate.

---

### Q5: SQLite doesn't have automatic TTL - who cleans up old metrics?

**Question:** SQLite has no built-in expiration. How do we prevent unbounded growth?

**Recommendation:**

**Time-based partitioning with automated cleanup:**

```python
# src/dashboard/metrics_cleanup.py

class MetricsRetentionManager:
    """
    Manages time-series data retention in SQLite.
    Default: Keep 7 days at full resolution, then aggregate.
    """
    
    RETENTION_DAYS = 7
    AGGREGATION_INTERVALS = [
        (7, 1),      # Days 1-7: 1-minute resolution
        (30, 5),     # Days 8-30: 5-minute resolution  
        (90, 60),    # Days 31-90: 1-hour resolution
        (365, 1440), # Days 91-365: 1-day resolution
    ]
    
    async def cleanup_old_metrics(self):
        """Run daily via APScheduler or cron."""
        async with aiosqlite.connect(self.db_path) as db:
            # 1. Delete data older than 1 year
            cutoff = datetime.utcnow() - timedelta(days=365)
            await db.execute(
                "DELETE FROM metrics WHERE timestamp < ?",
                (cutoff.isoformat(),)
            )
            
            # 2. Downsample old data to save space
            for days, minutes in self.AGGREGATION_INTERVALS:
                await self._downsample_metrics(db, days, minutes)
            
            # 3. Vacuum to reclaim space
            await db.execute("VACUUM")
            await db.commit()
    
    async def _downsample_metrics(self, db, age_days: int, interval_minutes: int):
        """
        Replace high-frequency old data with aggregates.
        """
        window_start = datetime.utcnow() - timedelta(days=age_days + 7)
        window_end = datetime.utcnow() - timedelta(days=age_days)
        
        # Calculate aggregates for each metric type
        await db.execute("""
            INSERT INTO metrics_downsampled (metric_type, timestamp, avg_value, min_value, max_value, count)
            SELECT 
                metric_type,
                strftime('%Y-%m-%d %H:%M:00', timestamp) as interval_start,
                AVG(value) as avg_value,
                MIN(value) as min_value,
                MAX(value) as max_value,
                COUNT(*) as count
            FROM metrics
            WHERE timestamp BETWEEN ? AND ?
            GROUP BY metric_type, interval_start
        """, (window_start.isoformat(), window_end.isoformat()))
        
        # Delete original high-frequency data
        await db.execute("""
            DELETE FROM metrics 
            WHERE timestamp BETWEEN ? AND ?
        """, (window_start.isoformat(), window_end.isoformat()))
```

**Scheduling:**
```python
# Run cleanup daily at 3 AM
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
scheduler.add_job(
    retention_manager.cleanup_old_metrics,
    trigger="cron",
    hour=3,
    minute=0
)
scheduler.start()
```

**Why not just DELETE:** Vacuum is expensive; better to downsample and keep trend data.

---

### Q6: Bot restart empties `_positions` dict - dashboard returns empty list or 503?

**Question:** During bot startup, `_recover_state()` hasn't completed. What should dashboard show?

**Recommendation:**

**Graceful degradation with explicit status:**

```python
# Bot exposes startup state
class BotState(Enum):
    STARTING = "starting"        # Process up, recovery not started
    RECOVERING = "recovering"    # Recovery in progress
    RUNNING = "running"          # Normal operation
    DEGRADED = "degraded"        # Running but some errors
    SHUTDOWN = "shutdown"        # Shutting down

# Dashboard API response during startup
{
    "bot": {
        "state": "recovering",
        "state_since": "2025-02-04T12:00:00Z",
        "recovery_progress": {
            "positions_found": 3,
            "positions_recovered": 2,
            "estimated_completion": "2025-02-04T12:00:05Z"
        }
    },
    "positions": [],  # Empty but not error
    "note": "Bot is recovering from previous state. Positions will appear shortly."
}
```

**Dashboard UI:**
- Show spinner with "Reconnecting to trading bot..."
- Display recovery progress if available
- Don't show "No positions" (implies actually zero positions)
- Auto-refresh every 2 seconds until state == "running"

**HTTP Status:** Return 200 OK with state metadata, not 503. The dashboard service is healthy, it's just waiting on the bot.

---

## Security Edge Cases

### Q7: API Key auth gives full access, JWT has roles - impedance mismatch

**Question:** Should bot accept JWT tokens, or should dashboard proxy with authorization layer?

**Recommendation:**

**Dashboard proxies and enforces RBAC:**

```python
# src/dashboard/api/control.py

@router.post("/control/pause")
async def pause_endpoint(
    request: PauseRequest,
    current_user: User = Depends(get_current_user)  # JWT auth
):
    """
    Dashboard enforces RBAC, then proxies to bot with admin key.
    Bot never sees JWT, only validates its own admin_api_key.
    """
    
    # 1. Dashboard enforces authorization
    if current_user.role not in ["operator", "admin"]:
        raise HTTPException(403, "Operators or admins only")
    
    if request.scope == "all" and current_user.role != "admin":
        raise HTTPException(403, "Only admins can fully pause")
    
    # 2. Audit log (dashboard responsibility)
    await audit_log.record(
        user=current_user.username,
        action="pause",
        scope=request.scope,
        reason=request.reason
    )
    
    # 3. Proxy to bot with admin key (dashboard knows this, user doesn't)
    result = await bot_bridge.pause(
        api_key=settings.bot_admin_key,  # Dashboard's stored secret
        reason=f"{current_user.username}: {request.reason}",
        scope=request.scope
    )
    
    return {"success": result}
```

**Benefits:**
- Bot keeps simple auth (single API key)
- Dashboard handles complex RBAC
- Audit trail captures who (JWT user) not just what
- Bot admin key never exposed to browser

---

### Q8: JWT expires mid-WebSocket connection - how to handle?

**Question:** Token expires at T+24h while connection is open. Options?

**Recommendation:**

**Silent refresh with dedicated endpoint:**

```python
class WebSocketManager:
    async def handle_connection(self, websocket: WebSocket, token: str):
        # 1. Validate initial token
        user = await self._validate_token(token)
        if not user:
            await websocket.close(code=4001, reason="Invalid token")
            return
        
        # 2. Track token expiration
        token_expires = user.exp
        refresh_threshold = token_expires - 300  # Refresh 5 min before expiry
        
        await websocket.accept()
        
        try:
            while True:
                # 3. Check if refresh needed before sending data
                if time.time() > refresh_threshold:
                    await websocket.send_json({
                        "type": "token_refresh_required",
                        "refresh_url": "/api/v1/auth/refresh"
                    })
                
                # Normal message handling
                msg = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0
                )
                
                if msg.get("action") == "refresh_token":
                    # Client sends new token
                    new_token = msg["token"]
                    user = await self._validate_token(new_token)
                    if user:
                        token_expires = user.exp
                        refresh_threshold = token_expires - 300
                        await websocket.send_json({
                            "type": "token_refresh_success"
                        })
                    else:
                        await websocket.close(code=4001)
                        return
                        
        except WebSocketDisconnect:
            pass
```

**Client-side:**
```javascript
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    
    if (msg.type === "token_refresh_required") {
        // Silently refresh in background
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

**Alternative (simpler):** Allow WebSocket to stay open but require valid token for sensitive operations. On operation, check token and reject if expired. Less secure but simpler.

---

### Q9: Both containers open same SQLite file - locking guarantees?

**Question:** SQLite file-level locking with multiple containers. Risks?

**Recommendation:**

**WAL mode + advisory locking:**

```python
# src/state/persistence.py modifications

class StatePersistence:
    async def setup(self):
        self._db = await aiosqlite.connect(self.db_path)
        
        # Enable WAL mode for better concurrency
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        
        # Short busy timeout (don't hang forever)
        await self._db.execute("PRAGMA busy_timeout=5000")  # 5 seconds
        
        await self._create_tables()
```

**Access patterns:**
- **Bot:** Read-write (positions, actions)
- **Dashboard:** Read-only via `mode=ro` connection

```python
# Dashboard connects read-only
db = await aiosqlite.connect(
    "/app/data/state.db",
    uri=True,
    # Read-only mode prevents any write locks
)
```

**File permissions:**
```dockerfile
# Dockerfile.dashboard
RUN chmod 444 /app/data/state.db  # Read-only for dashboard user
```

**Monitoring:**
```python
# Alert if WAL file grows too large
async def check_wal_size():
    wal_path = "/app/data/state.db-wal"
    if os.path.exists(wal_path):
        size_mb = os.path.getsize(wal_path) / (1024 * 1024)
        if size_mb > 100:  # 100MB
            logger.warning(f"WAL file large: {size_mb:.1f}MB - checkpoint needed")
            # Bot should run: PRAGMA wal_checkpoint(TRUNCATE)
```

**When to migrate to PostgreSQL:**
- WAL file consistently > 500MB
- Checkpoint operations taking > 5 seconds
- Need for concurrent writes from dashboard

---

## Alerting & Notifications

### Q10: Health factor template formatting - `:.2%` gives 2500%

**Question:** `health_factor: 0.25` formatted as `:.2%` becomes `2500.00%`. Correct approach?

**Recommendation:**

**Use decimal format, not percentage:**

```python
TELEGRAM_TEMPLATES = {
    "health_factor_critical": """
🚨 <b>CRITICAL: Health Factor Alert</b>

Position: {position_id}
Asset: {asset}
Health Factor: {health_factor:.2%} ❌ WRONG - gives 2500%
Health Factor: {health_factor:.4f} ✅ CORRECT - gives 0.2500
Health Factor: {health_factor_percentage:.1f}% ✅ ALTERNATIVE - gives 25.0%
"""
}

# In alert engine:
health_factor_decimal = 0.25
health_factor_percentage = health_factor_decimal * 100

message = template.format(
    health_factor=health_factor_decimal,  # For :.4f
    health_factor_percentage=health_factor_percentage  # For :.1f%
)
```

**Clarity guidelines:**
- Use `0.25` (25%) format for technical users who know HF scale
- Use `25.0%` for human-readable alerts
- Always include context: "Liquidation at 0% (current: 25%)"

---

### Q11: Alert throttling vs critical escalation

**Question:** 5-minute throttle misses rapid health factor degradation. Solution?

**Recommendation:**

**Progressive severity with per-metric throttling:**

```python
class AlertEngine:
    def __init__(self):
        # Separate throttle per (metric, severity) combination
        self._last_alert = {}  # {(metric_id, severity): timestamp}
    
    async def check_health_factor(self, position: Position):
        hf = position.asgard.current_health_factor
        
        # Progressive severity levels
        if hf < 0.10:
            severity = "CRITICAL"
            metric_key = f"{position.id}_liquidation_imminent"
            throttle = 0  # No throttle - every update
            
        elif hf < 0.15:
            severity = "CRITICAL"
            metric_key = f"{position.id}_hf_critical"
            throttle = 60  # 1 minute max
            
        elif hf < 0.20:
            severity = "WARNING"
            metric_key = f"{position.id}_hf_warning"
            throttle = 300  # 5 minutes
            
        else:
            return  # No alert
        
        # Check if we should send
        last_sent = self._last_alert.get((metric_key, severity), 0)
        if time.time() - last_sent < throttle:
            return
        
        await self._send_alert(metric_key, severity, position)
        self._last_alert[(metric_key, severity)] = time.time()
```

**Alert flow example:**
```
T+0: HF = 0.18 → WARNING sent (throttle 5min)
T+1: HF = 0.14 → CRITICAL sent immediately (different severity, different key)
T+2: HF = 0.09 → LIQUIDATION_IMMINENT sent immediately (no throttle)
T+3: HF = 0.08 → LIQUIDATION_IMMINENT sent (no throttle, severity unchanged)
```

---

### Q12: Telegram bot command spam - rate limiting

**Question:** `/status` flood from Telegram could DoS bot. Protection?

**Recommendation:**

**Per-user rate limiting with exponential backoff:**

```python
from collections import defaultdict
import time

class TelegramRateLimiter:
    def __init__(self):
        # Track per-user command history
        self._user_commands = defaultdict(list)
        self._limits = {
            "status": (5, 60),      # 5 per minute
            "pause": (3, 300),      # 3 per 5 minutes
            "resume": (3, 300),     # 3 per 5 minutes
            "default": (10, 60)     # 10 per minute
        }
    
    def is_allowed(self, user_id: str, command: str) -> tuple[bool, str]:
        """Returns (allowed, error_message)."""
        now = time.time()
        window = 60  # 1 minute window
        
        # Get user's command history
        history = self._user_commands[user_id]
        
        # Clean old entries
        history = [t for t in history if now - t < window]
        self._user_commands[user_id] = history
        
        # Check limits
        max_calls, period = self._limits.get(command, self._limits["default"])
        recent_calls = len(history)
        
        if recent_calls >= max_calls:
            retry_after = int(window - (now - history[0]))
            return False, f"Rate limit exceeded. Try again in {retry_after}s."
        
        # Record this command
        history.append(now)
        return True, ""

# In Telegram handler:
@telegram_router.message(Command("status"))
async def status_command(message: Message):
    allowed, error = rate_limiter.is_allowed(
        str(message.from_user.id), 
        "status"
    )
    
    if not allowed:
        await message.reply(error)
        return
    
    # Process command...
```

**Additional protections:**
- Global rate limit: 100 commands/minute across all users
- IP-based limiting for webhook endpoints
- Command queue with prioritization (pause/resume > status)

---

## UX & Operational Reality

### Q13: Mobile horizontal scroll conflicts with browser back gesture

**Question:** Mobile browsers hijack horizontal swipe. Alternative navigation?

**Recommendation:**

**Vertical accordion + optional horizontal with visual affordance:**

```html
<!-- Mobile view -->
<div class="mobile-dashboard">
    <!-- Status cards: Vertical stack with expand/collapse -->
    <div class="status-section" onclick="this.classList.toggle('expanded')">
        <h3>Status Overview ▼</h3>
        <div class="status-grid">
            <div class="card">Uptime: 24:00:00</div>
            <div class="card">Positions: 3</div>
            <div class="card">PnL: +$123</div>
        </div>
    </div>
    
    <!-- Positions: Accordion list -->
    <div class="positions-section">
        <h3>Positions (3)</h3>
        <details class="position-card">
            <summary>SOL | 3x | +$45</summary>
            <div class="position-details">
                <p>Health Factor: 28%</p>
                <p>Delta: $12.50</p>
            </div>
        </details>
    </div>
</div>

<style>
/* Prevent browser back gesture on dashboard area */
.mobile-dashboard {
    overscroll-behavior-x: none;
    touch-action: pan-y;  /* Only vertical scroll */
}

/* But allow horizontal scroll on charts with visual indicator */
.chart-container {
    touch-action: pan-x pan-y;
    position: relative;
}

.chart-container::after {
    content: "↔ Swipe to pan";
    position: absolute;
    bottom: 10px;
    right: 10px;
    background: rgba(0,0,0,0.5);
    color: white;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
}
</style>
```

**Key interactions:**
- **Cards:** Vertical stack (no horizontal scroll)
- **Charts:** Explicit pan indicator, both-axis touch
- **Tables:** Horizontal scroll with sticky first column
- **Swipe back:** Disabled on dashboard (`overscroll-behavior-x: none`)

---

### Q14: PnL chart timezone ambiguity

**Question:** "24h" tab means different things in different timezones. Standard?

**Recommendation:**

**UTC for data, local for display:**

```python
# API always returns UTC timestamps
{
    "data_points": [
        {
            "timestamp": "2025-02-04T12:00:00Z",  # UTC
            "total_pnl": 123.45
        }
    ],
    "timezone": "UTC",
    "period": "24h"  # Last 24 hours from now, not calendar day
}
```

```javascript
// Client converts to local time
const localTime = new Date(dataPoint.timestamp).toLocaleString();

// Or show both
function formatTime(utcTimestamp) {
    const date = new Date(utcTimestamp);
    return {
        local: date.toLocaleTimeString(),
        utc: date.toISOString().split('T')[1].slice(0, 5) + ' UTC',
        relative: timeAgo(date)  // "2 hours ago"
    };
}
```

**UI pattern:**
```
PnL (24h)                    [?]
Last updated: 2:34 PM EST    [UTC: 19:34]
```

**Period definitions:**
- "24h" = Rolling 24 hours (now - 24h)
- "Today" = Calendar day in user's timezone (00:00 - 23:59)
- "Daily" = UTC calendar day (crypto standard)

Default to rolling windows for "24h/7d/30d" to avoid timezone confusion.

---

### Q15: Emergency Stop button - preventing accidental clicks

**Question:** Confirmation dialog adds friction, no confirmation is dangerous. Balance?

**Recommendation:**

**Progressive friction based on impact:**

```html
<!-- Level 1: Pause Entry (low impact) -->
<button onclick="pauseEntry()" class="btn-warning">
    Pause Entry
</button>

<!-- Level 2: Pause All (medium impact) - Single confirmation -->
<button onclick="confirmPauseAll()" class="btn-warning">
    Pause All
</button>

<script>
function confirmPauseAll() {
    if (confirm("Pause all bot operations?\n\nExisting positions will remain open.")) {
        pauseAll();
    }
}
</script>

<!-- Level 3: Emergency Stop (high impact) - Multi-step + hold -->
<div class="emergency-stop-container">
    <button 
        id="emergencyBtn"
        onmousedown="startEmergencyHold()"
        onmouseup="cancelEmergencyHold()"
        onmouseleave="cancelEmergencyHold()"
        class="btn-danger"
    >
        🔴 EMERGENCY STOP
        <span id="holdProgress"></span>
    </button>
    <p class="hint">Hold for 3 seconds to confirm</p>
</div>

<script>
let holdTimer = null;
const HOLD_DURATION = 3000;

function startEmergencyHold() {
    const btn = document.getElementById('emergencyBtn');
    const progress = document.getElementById('holdProgress');
    
    let elapsed = 0;
    holdTimer = setInterval(() => {
        elapsed += 100;
        const pct = (elapsed / HOLD_DURATION) * 100;
        progress.style.width = pct + '%';
        
        if (elapsed >= HOLD_DURATION) {
            clearInterval(holdTimer);
            executeEmergencyStop();
        }
    }, 100);
}

function cancelEmergencyHold() {
    if (holdTimer) {
        clearInterval(holdTimer);
        document.getElementById('holdProgress').style.width = '0%';
    }
}

async function executeEmergencyStop() {
    // Double-confirm for emergency
    const confirmed = await showModal({
        title: "⚠️ CONFIRM EMERGENCY STOP",
        message: "This will:\n• Close all positions immediately\n• Cancel all pending orders\n• Require manual restart\n\nThis action CANNOT be undone.",
        confirmText: "YES, STOP EVERYTHING",
        confirmClass: "btn-danger",
        requireTyping: "STOP"  // Type to confirm
    });
    
    if (confirmed) {
        await api.post('/control/emergency-stop');
    }
}
</script>
```

**Friction scale:**
| Action | Friction | Time to execute |
|--------|----------|-----------------|
| Pause Entry | None | Instant |
| Pause All | Click + Confirm | 2 seconds |
| Emergency Stop | Hold 3s + Modal + Type "STOP" | 8-10 seconds |

**Additional safety:**
- Emergency stop requires re-authentication if session > 15 minutes old
- Send confirmation email/Telegram after emergency stop
- Log emergency stop with IP address and user agent

---

## Error Handling & Edge Cases

### Q16: WebSocket disconnect - missed updates, how to catch up?

**Question:** Client disconnects, misses updates, reconnects. Gap recovery?

**Recommendation:**

**Event sourcing with sequence numbers:**

```python
class EventStore:
    """
    Keeps last N events in memory for catch-up.
    For production, use Redis stream or database.
    """
    
    def __init__(self, max_events: int = 10000):
        self._events = deque(maxlen=max_events)
        self._sequence = 0
    
    def append(self, event: dict):
        self._sequence += 1
        event["seq"] = self._sequence
        event["timestamp"] = datetime.utcnow().isoformat()
        self._events.append(event)
        return self._sequence
    
    def get_since(self, last_seq: int) -> List[dict]:
        """Get all events after given sequence number."""
        return [e for e in self._events if e["seq"] > last_seq]

# WebSocket protocol:
{
    "type": "subscribe",
    "last_seq": 1234  # Client's last known event
}

# Server response:
{
    "type": "catch_up",
    "events": [...],  # Missed events
    "new_seq": 1240   # Latest sequence
}
```

**Client reconnect logic:**
```javascript
class ResilientWebSocket {
    constructor(url) {
        this.url = url;
        this.lastSeq = 0;
        this.reconnectDelay = 1000;
    }
    
    connect() {
        this.ws = new WebSocket(this.url);
        
        this.ws.onopen = () => {
            // Subscribe with last known sequence
            this.ws.send(JSON.stringify({
                action: "subscribe",
                last_seq: this.lastSeq
            }));
            this.reconnectDelay = 1000;  // Reset backoff
        };
        
        this.ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            
            if (msg.seq) {
                this.lastSeq = msg.seq;
            }
            
            if (msg.type === "catch_up") {
                // Apply missed events in order
                msg.events.forEach(e => this.handleEvent(e));
            } else {
                this.handleEvent(msg);
            }
        };
        
        this.ws.onclose = () => {
            // Exponential backoff reconnect
            setTimeout(() => this.connect(), this.reconnectDelay);
            this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
        };
    }
}
```

**Fallback:** If gap > 10,000 events (too old), force full snapshot instead of catch-up.

---

### Q17: BotBridge with None bot - API calls before bot ready

**Question:** `BotBridge` initialized before bot is ready. Failure mode?

**Recommendation:**

**Fail fast with clear error codes:**

```python
class BotBridge:
    def __init__(self, bot_api_url: str):
        self._api_url = bot_api_url
        self._bot_ready = False
        self._last_health_check = 0
    
    async def _ensure_bot_ready(self):
        """Check bot health before operations."""
        now = time.time()
        
        # Cache health check for 5 seconds
        if now - self._last_health_check < 5 and self._bot_ready:
            return
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._api_url}/health",
                    timeout=2.0
                )
                self._bot_ready = response.status_code == 200
        except Exception:
            self._bot_ready = False
        
        self._last_health_check = now
        
        if not self._bot_ready:
            raise BotUnavailableError("Bot is starting up or unavailable")
    
    async def get_positions(self) -> Dict:
        await self._ensure_bot_ready()
        
        try:
            response = await self._client.get("/internal/positions")
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            self._bot_ready = False
            raise BotUnavailableError("Cannot connect to bot")
```

**HTTP responses:**
```python
# Dashboard API returns clear status
@app.get("/api/v1/positions")
async def get_positions():
    try:
        positions = await bot_bridge.get_positions()
        return {"positions": positions, "source": "live"}
    except BotUnavailableError:
        return JSONResponse(
            status_code=503,
            content={
                "error": "Bot unavailable",
                "message": "Trading bot is starting up or recovering",
                "retry_after": 5,
                "cached_data": await get_cached_positions()  # Stale but useful
            }
        )
```

---

### Q18: Circuit breaker triggers but WebSocket broadcast fails

**Question:** User only watching UI, WebSocket dead, doesn't know bot paused. How to ensure visibility?

**Recommendation:**

**Multi-channel persistence with visual indicators:**

```python
class CircuitBreakerNotifier:
    async def on_circuit_breaker(self, event: CircuitBreakerEvent):
        # 1. Try WebSocket (may fail)
        await self._try_websocket_broadcast(event)
        
        # 2. Always update database (source of truth)
        await self._persist_state_change(event)
        
        # 3. Send push notification (if subscribed)
        await self._send_push_notification(event)
        
        # 4. Set persistent banner flag
        await self._set_system_banner(
            level="critical",
            message=f"Bot PAUSED: {event.reason}",
            dismissible=False  # Must acknowledge
        )
```

**UI pattern - Persistent banner:**
```html
<!-- Survives page refresh, cleared only by explicit resume -->
<div id="system-banner" class="banner-critical" data-persistent="true">
    🔴 <strong>SYSTEM PAUSED</strong>
    <span>Circuit breaker: negative_apy</span>
    <button onclick="acknowledgePause()">Acknowledge</button>
</div>

<script>
// On page load, check for persistent banners
async function checkSystemState() {
    const state = await fetch('/api/v1/pause-state').then(r => r.json());
    
    if (state.paused && !state.acknowledged) {
        showPersistentBanner({
            level: "critical",
            message: state.reason,
            dismissible: false
        });
    }
}

// Poll every 10 seconds as fallback
setInterval(checkSystemState, 10000);
</script>
```

**Escalation path:**
1. WebSocket (immediate, but unreliable)
2. Database persistence (survives refresh)
3. Polling fallback (catches missed events)
4. Push notification (alerts even if browser closed)
5. Email for critical alerts (last resort)

---

## Performance & Scale

### Q19: Metrics table grows to 2M+ rows - SELECTs for charting slow

**Question:** SQLite performance degrades with millions of metrics rows. Solutions?

**Recommendation:**

**Downsampling strategy (already described in Q5) + query optimization:**

```python
class MetricsQuery:
    """
    Smart query routing based on time range.
    """
    
    async def get_pnl_history(
        self,
        days: int,
        resolution: str = "auto"
    ) -> List[dict]:
        """
        Automatically select appropriate table based on query range.
        """
        if resolution == "auto":
            resolution = self._select_resolution(days)
        
        table = self._get_table_for_resolution(resolution)
        
        # Pre-aggregated data for large ranges
        query = f"""
            SELECT 
                timestamp,
                AVG(value) as value,
                MIN(value) as min_value,
                MAX(value) as max_value
            FROM {table}
            WHERE metric_type = 'pnl'
              AND timestamp > datetime('now', '-{days} days')
            GROUP BY strftime('{self._get_groupby(resolution)}', timestamp)
            ORDER BY timestamp
        """
        
        return await self._execute(query)
    
    def _select_resolution(self, days: int) -> str:
        """Choose resolution based on query range."""
        if days <= 1:
            return "1min"   # 1,440 points
        elif days <= 7:
            return "5min"   # 2,016 points  
        elif days <= 30:
            return "1hour"  # 720 points
        else:
            return "1day"   # 365 points max
```

**Hard limits:**
- Chart max 2000 data points (browser performance)
- Query timeout: 5 seconds
- Auto-downsample if raw query too slow

---

### Q20: WebSocket broadcast to 100 clients - 20,000 msgs/minute efficient?

**Question:** FastAPI's default WebSocket can handle this, but should we optimize?

**Recommendation:**

**Optimize with message batching and binary protocol:**

```python
import msgpack  # Binary JSON alternative

class OptimizedWebSocketManager:
    def __init__(self):
        self._connections = set()
        self._batch_queue = []
        self._batch_timer = None
        self._use_msgpack = True  # Negotiate with client
    
    async def broadcast(self, message: dict, urgent: bool = False):
        """
        Batch non-urgent messages, send urgent immediately.
        """
        if urgent:
            await self._send_immediately(message)
        else:
            self._batch_queue.append(message)
            
            # Start batch timer if not running
            if self._batch_timer is None:
                self._batch_timer = asyncio.create_task(
                    self._flush_batch_after(0.1)  # 100ms batch window
                )
    
    async def _flush_batch_after(self, delay: float):
        await asyncio.sleep(delay)
        
        if self._batch_queue:
            batch = {
                "type": "batch",
                "messages": self._batch_queue,
                "count": len(self._batch_queue)
            }
            await self._send_to_all(batch)
            self._batch_queue = []
        
        self._batch_timer = None
    
    async def _send_to_all(self, message: dict):
        """Send with msgpack compression."""
        if self._use_msgpack:
            payload = msgpack.packb(message, use_bin_type=True)
            headers = {"content-type": "application/msgpack"}
        else:
            payload = json.dumps(message).encode()
            headers = {"content-type": "application/json"}
        
        # Concurrent send with gather
        tasks = []
        for conn in self._connections:
            tasks.append(self._send_safe(conn, payload, headers))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clean up disconnected clients
        for conn, result in zip(self._connections.copy(), results):
            if isinstance(result, Exception):
                self._connections.discard(conn)
```

**Benchmarks:**
- JSON: ~200 bytes per position update
- Msgpack: ~120 bytes (40% reduction)
- Batching 10 updates: 1 frame instead of 10 (header overhead reduction)

**Connection limits:**
```python
# Hard limit to prevent resource exhaustion
MAX_WEBSOCKET_CONNECTIONS = 500

async def connect(self, websocket: WebSocket):
    if len(self._connections) >= MAX_WEBSOCKET_CONNECTIONS:
        await websocket.close(code=1013, reason="Server overload")
        return
    
    await websocket.accept()
    self._connections.add(websocket)
```

---

## Deployment & Operations

### Q21: Caddy rate limiting uses static key - all users share bucket

**Question:** Current Caddyfile uses `key static` - one bucket for all users. Per-user limiting?

**Recommendation:**

**Replace Caddy rate limit with application-level per-user limiting:**

```python
# src/dashboard/middleware/rate_limit.py

from fastapi import Request, HTTPException
from collections import defaultdict
import time

class RateLimiter:
    def __init__(self):
        self._requests = defaultdict(list)  # {user_id: [timestamp, ...]}
        self._limits = {
            "viewer": (100, 60),      # 100/min
            "operator": (200, 60),    # 200/min
            "admin": (500, 60),       # 500/min
        }
    
    async def check_rate_limit(self, request: Request, user: User):
        """Apply per-user rate limiting."""
        now = time.time()
        window = 60
        
        max_reqs, _ = self._limits.get(user.role, self._limits["viewer"])
        
        # Clean old entries
        history = self._requests[user.id]
        history = [t for t in history if now - t < window]
        self._requests[user.id] = history
        
        if len(history) >= max_reqs:
            retry_after = int(window - (now - history[0]))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)}
            )
        
        history.append(now)

# Remove rate_limit from Caddyfile - let app handle it
# Caddyfile:
dashboard.yourdomain.com {
    reverse_proxy dashboard:8080
    # Rate limiting handled by FastAPI middleware
}
```

**IP-based limiting for unauthenticated endpoints:**
```python
# Stricter limits for login attempts
@app.post("/api/v1/auth/login")
@rate_limit_by_ip(max_requests=5, window=300)  # 5 per 5 min
def login(credentials: LoginRequest):
    ...
```

---

### Q22: Dashboard healthcheck pings itself - doesn't verify bot connectivity

**Question:** Dashboard returns 200 OK even if bot is down. Better healthcheck?

**Recommendation:**

**Comprehensive healthcheck with dependency verification:**

```python
@app.get("/api/v1/health")
async def health_check():
    """
    Detailed health status for monitoring and load balancers.
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
        bot_health = await bot_bridge.health_check()
        checks["bot_api"]["response_time_ms"] = int((time.time() - start) * 1000)
        checks["bot_api"]["status"] = "healthy" if bot_health else "degraded"
        if not bot_health:
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
    
    # Return appropriate status code
    status_code = {
        "healthy": 200,
        "degraded": 200,  # Still serving, but issues
        "unhealthy": 503
    }[overall_status]
    
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

**Docker healthcheck:**
```yaml
healthcheck:
  test: [
    "CMD", "curl", "-f", 
    "http://localhost:8080/api/v1/health",
    "--max-time", "5"
  ]
  interval: 30s
  timeout: 5s
  retries: 3
```

**Kubernetes-style readiness check:**
- `/health` - Liveness (restart if failing)
- `/ready` - Readiness (remove from LB if failing)

---

### Q23: Log aggregation across bot + dashboard + proxy - correlation

**Question:** Three containers, three log streams. How to correlate a "pause" action across them?

**Recommendation:**

**Structured logging with correlation IDs:**

```python
# Shared logging configuration
import structlog
import uuid

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

# Generate correlation ID at entry point
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    
    # Bind to context for all logs in this request
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        user_agent=request.headers.get("user-agent"),
        client_ip=request.client.host
    )
    
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response

# Usage in dashboard:
@app.post("/api/v1/control/pause")
async def pause(request: PauseRequest):
    logger = structlog.get_logger()
    
    logger.info("Pause requested", 
                reason=request.reason, 
                user=request.user.username)
    
    # Propagate correlation ID to bot
    result = await bot_bridge.pause(
        api_key=settings.bot_admin_key,
        reason=request.reason,
        correlation_id=structlog.contextvars.get_contextvars().get("correlation_id")
    )
    
    logger.info("Pause executed", success=result)
```

**Log format (all services):**
```json
{
  "timestamp": "2025-02-04T12:00:00Z",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "service": "dashboard|bot|proxy",
  "level": "info",
  "event": "Pause requested",
  "user": "admin",
  "reason": "Manual maintenance"
}
```

**Query example:**
```bash
# Find all logs for a specific action
docker-compose logs -t | jq 'select(.correlation_id == "550e8400...")'

# Or with centralized logging (Loki/ELK)
{correlation_id="550e8400-e29b-41d4-a716-446655440000"}
```

**Request flow tracing:**
```
User → Caddy (adds X-Request-ID)
     → Dashboard (adds X-Correlation-ID)
         → Bot API (logs with correlation_id)
     → Response (includes both IDs)
```

---

## Summary Checklist

Review these decisions and mark any changes:

| Decision | My Recommendation | Your Decision |
|----------|-------------------|---------------|
| **Q1** | Stale-data cache (5s TTL) | |
| **Q2** | Separate containers + HTTP API | |
| **Q3** | Fire-and-forget with circuit breaker | |
| **Q4** | Snapshot + delta pattern | |
| **Q5** | Time-based downsampling, daily cleanup | |
| **Q6** | Graceful degradation with startup state | |
| **Q7** | Dashboard proxies, enforces RBAC | |
| **Q8** | Silent refresh over WebSocket | |
| **Q9** | WAL mode + read-only dashboard | |
| **Q10** | Decimal format (0.25) or percentage (25%) | |
| **Q11** | Progressive severity, no throttle on critical | |
| **Q12** | Per-user rate limiting | |
| **Q13** | Vertical accordion + explicit pan indicators | |
| **Q14** | UTC data, local display, rolling windows | |
| **Q15** | Progressive friction (hold 3s + type "STOP") | |
| **Q16** | Event sourcing with sequence numbers | |
| **Q17** | Fail fast with 503 + cached data | |
| **Q18** | Persistent banner + polling fallback | |
| **Q19** | Auto-downsampling by query range | |
| **Q20** | Msgpack + batching + 500 conn limit | |
| **Q21** | App-level per-user rate limiting | |
| **Q22** | Comprehensive healthcheck with deps | |
| **Q23** | Structured JSON logs + correlation IDs | |

**Next steps:**
1. Mark any recommendations you disagree with
2. Add alternative approaches where needed
3. Prioritize which decisions are "must have" vs "can iterate"
4. I'll update the spec with finalized decisions
