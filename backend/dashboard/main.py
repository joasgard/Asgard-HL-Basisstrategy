"""
Asgard Basis Dashboard - FastAPI application.

API backend for React SPA frontend:
- JSON API endpoints at /api/v1/*
- Serves React static files at /*
- Privy handles authentication
- PostgreSQL + Redis for shared state
"""

import os
import sys
import signal
import asyncio
import uuid
import time
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.dashboard.config import get_dashboard_settings
from backend.dashboard.bot_bridge import BotBridge
from backend.dashboard.dependencies import (
    set_bot_bridge, get_bot_bridge,
    set_position_monitor, get_position_monitor,
    set_intent_scanner, get_intent_scanner,
)
from backend.dashboard.events_manager import event_manager
from shared.db.database import get_db, init_db
from shared.db.migrations import run_migrations
from bot.core.errors import register_exception_handlers
from bot.core.position_monitor import PositionMonitorService
from bot.core.intent_scanner import IntentScanner

# Import API routers
from backend.dashboard.api import status, positions, control, rates, settings as settings_api
from backend.dashboard.api import auth as auth_api, balances as balances_api, events as events_api
from backend.dashboard.api import wallet_setup as wallet_setup_api
from backend.dashboard.api import intents as intents_api

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job recovery
# ---------------------------------------------------------------------------

async def _recover_stuck_jobs(db) -> int:
    """On startup, mark jobs stuck in 'running' status as failed."""
    rows = await db.fetchall(
        "SELECT job_id FROM position_jobs WHERE status = 'running'"
    )
    count = 0
    for row in rows:
        await db.execute(
            """UPDATE position_jobs
               SET status = 'failed', last_error = 'Server restarted while job was running',
                   completed_at = NOW()
               WHERE job_id = $1""",
            (row["job_id"],),
        )
        count += 1
    if count:
        logger.warning("Recovered %d stuck jobs on startup", count)
    return count


# ---------------------------------------------------------------------------
# Distributed lock helpers
# ---------------------------------------------------------------------------

async def _acquire_service_lock(redis, name: str, ttl: int = 60) -> bool:
    """Acquire a Redis-based distributed lock for a background service."""
    key = f"lock:{name}"
    return await redis.set(key, "1", nx=True, ex=ttl)


async def _release_service_lock(redis, name: str) -> None:
    """Release a distributed lock."""
    await redis.delete(f"lock:{name}")


async def _refresh_service_lock(redis, name: str, ttl: int = 60) -> None:
    """Refresh the TTL on a distributed lock."""
    await redis.expire(f"lock:{name}", ttl)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    settings = get_dashboard_settings()

    # Configure structured JSON logging
    _configure_logging(settings.log_level)

    logger.info("Starting dashboard API...")

    # Initialize database (PostgreSQL)
    logger.info("Connecting to PostgreSQL...")
    db = await init_db(settings.database_url)

    # Run migrations
    logger.info("Running database migrations...")
    try:
        version = await run_migrations(db)
        logger.info(f"Database schema version: {version}")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

    # Recover stuck jobs from previous crash
    await _recover_stuck_jobs(db)

    # Initialize Redis
    logger.info("Connecting to Redis...")
    from shared.redis_client import get_redis
    redis = await get_redis(settings.redis_url)
    try:
        await redis.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise

    # Wire session manager with DB
    from backend.dashboard.auth import session_manager
    session_manager.set_db(db)

    # Initialize event manager for SSE (now with Redis pub/sub)
    logger.info("Initializing event manager...")
    await event_manager.start()

    # Initialize bot bridge
    logger.info("Initializing bot bridge...")
    try:
        bot_bridge = BotBridge(
            bot_api_url=settings.bot_api_url,
            internal_token=settings.internal_token
        )
        await bot_bridge.start()
        set_bot_bridge(bot_bridge)
        logger.info(f"Connected to bot at {settings.bot_api_url}")
    except Exception as e:
        logger.warning(f"Bot bridge not available: {e}")

    # Start position monitor service (with distributed lock)
    logger.info("Starting position monitor service...")
    try:
        monitor = PositionMonitorService(db=db)
        await monitor.start()
        set_position_monitor(monitor)
        logger.info("Position monitor service started")
    except Exception as e:
        logger.warning(f"Position monitor not started: {e}")

    # Start intent scanner service (with distributed lock)
    logger.info("Starting intent scanner service...")
    try:
        scanner = IntentScanner(db=db)
        await scanner.start()
        set_intent_scanner(scanner)
        logger.info("Intent scanner service started")
    except Exception as e:
        logger.warning(f"Intent scanner not started: {e}")

    logger.info("Dashboard API ready")

    yield

    # ------------------------------------------------------------------
    # Graceful shutdown
    # ------------------------------------------------------------------
    logger.info("Shutting down dashboard...")

    # Stop intent scanner
    try:
        scanner = get_intent_scanner()
        if scanner:
            await scanner.stop()
    except Exception:
        pass

    # Stop position monitor
    try:
        monitor = get_position_monitor()
        if monitor:
            await monitor.stop()
    except Exception:
        pass

    try:
        bridge = get_bot_bridge()
        if bridge:
            await bridge.stop()
    except Exception:
        pass

    # Stop event manager
    try:
        await event_manager.stop()
    except Exception:
        pass

    # Release distributed locks
    try:
        redis = await get_redis()
        await _release_service_lock(redis, "monitor")
        await _release_service_lock(redis, "scanner")
    except Exception:
        pass

    # Close Redis
    try:
        from shared.redis_client import close_redis
        await close_redis()
    except Exception:
        pass

    # Close database
    await db.close()
    logger.info("Dashboard stopped")


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

def _configure_logging(level: str = "INFO"):
    """Configure structured JSON logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                "timestamp": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            # Add request_id and user_id if present
            if hasattr(record, "request_id"):
                log_entry["request_id"] = record.request_id
            if hasattr(record, "user_id"):
                log_entry["user_id"] = record.user_id
            if record.exc_info and record.exc_info[0] is not None:
                log_entry["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_entry)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_dashboard_settings()

    app = FastAPI(
        title="Asgard Basis API",
        description="API backend for Asgard Basis React frontend",
        version="0.3.0",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Request ID middleware
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # ------------------------------------------------------------------
    # Request logging middleware
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        # Skip health endpoints
        if request.url.path.startswith("/health"):
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 1),
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        return response

    # ------------------------------------------------------------------
    # Security headers middleware
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # ------------------------------------------------------------------
    # Global exception handler
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def global_error_handler(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            request_id = getattr(request.state, "request_id", None)
            logger.error(
                "Unhandled exception",
                extra={"request_id": request_id, "path": request.url.path},
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
            )

    # ------------------------------------------------------------------
    # Rate limiting middleware (Redis-backed)
    # ------------------------------------------------------------------
    from backend.dashboard.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)

    # ------------------------------------------------------------------
    # CORS middleware — configurable via ALLOWED_ORIGINS env var
    # ------------------------------------------------------------------
    allowed_origins = settings.get_allowed_origins_list()
    if settings.dashboard_env == "development":
        # Add common dev origins explicitly — never use "*" with credentials
        dev_origins = [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]
        for origin in dev_origins:
            if origin not in allowed_origins:
                allowed_origins.append(origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Register exception handlers for structured error responses
    register_exception_handlers(app)

    # Include API routers
    app.include_router(status.router, prefix="/api/v1")
    app.include_router(positions.router, prefix="/api/v1")
    app.include_router(control.router, prefix="/api/v1")
    app.include_router(rates.router, prefix="/api/v1")
    app.include_router(settings_api.router, prefix="/api/v1")
    app.include_router(auth_api.router, prefix="/api/v1/auth")
    app.include_router(balances_api.router, prefix="/api/v1")
    app.include_router(events_api.router, prefix="/api/v1")
    app.include_router(wallet_setup_api.router, prefix="/api/v1")
    app.include_router(intents_api.router, prefix="/api/v1")

    # ------------------------------------------------------------------
    # Health check endpoints
    # ------------------------------------------------------------------
    @app.get("/health")
    @app.get("/health/live")
    async def health_live():
        """Liveness probe — process is alive."""
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready():
        """
        Readiness probe — DB + Redis connected, background services running.
        """
        checks = {}

        # Database check
        db = get_db()
        try:
            await db.execute("SELECT 1")
            checks["database"] = "healthy"
        except Exception:
            checks["database"] = "error"

        # Redis check
        try:
            from shared.redis_client import get_redis
            redis = await get_redis()
            await redis.ping()
            checks["redis"] = "healthy"
        except Exception:
            checks["redis"] = "error"

        # Bot bridge
        bridge = get_bot_bridge()
        bot_healthy = False
        if bridge:
            try:
                bot_healthy = await bridge.health_check()
            except Exception:
                pass
        checks["bot_connected"] = bot_healthy

        # Background services
        monitor = get_position_monitor()
        scanner = get_intent_scanner()
        checks["position_monitor"] = "running" if monitor and monitor._running else "stopped"
        checks["intent_scanner"] = "running" if scanner and scanner._running else "stopped"

        all_healthy = (
            checks["database"] == "healthy"
            and checks["redis"] == "healthy"
        )

        return {
            "status": "ready" if all_healthy else "not_ready",
            **checks,
        }

    # ------------------------------------------------------------------
    # Serve React frontend
    # ------------------------------------------------------------------
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    frontend_dist = os.path.join(project_root, "frontend", "dist")

    if os.path.exists(frontend_dist):
        app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

        for item in os.listdir(frontend_dist):
            if item != "assets":
                item_path = os.path.join(frontend_dist, item)
                if os.path.isfile(item_path):
                    app.mount(f"/{item}", StaticFiles(directory=frontend_dist), name=item)

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            """Serve React SPA index.html for all routes (client-side routing)."""
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)

            # Prevent path traversal: resolve and verify path stays within frontend_dist
            file_path = os.path.realpath(os.path.join(frontend_dist, path))
            dist_realpath = os.path.realpath(frontend_dist)
            if not file_path.startswith(dist_realpath + os.sep) and file_path != dist_realpath:
                return JSONResponse({"detail": "Not found"}, status_code=404)

            if os.path.isfile(file_path):
                return FileResponse(file_path)

            index_path = os.path.join(frontend_dist, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            else:
                return JSONResponse(
                    {"error": "Frontend not built. Run 'npm run build' in frontend/"},
                    status_code=500
                )
    else:
        @app.get("/")
        async def root():
            return {
                "message": "Asgard Basis API",
                "status": "Frontend not built",
                "instructions": "Run 'cd frontend && npm run build' to build the React app",
                "api_docs": "/docs",
            }

    return app


# Create the app instance
app = create_app()
