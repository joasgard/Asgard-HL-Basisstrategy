"""
Delta Neutral Bot Dashboard - FastAPI application.

API backend for React SPA frontend:
- JSON API endpoints at /api/v1/*
- Serves React static files at /*
- Privy handles authentication
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from src.dashboard.config import get_dashboard_settings
from src.dashboard.bot_bridge import BotBridge
from src.dashboard.dependencies import set_bot_bridge, get_bot_bridge
from src.dashboard.events_manager import event_manager
from src.db.database import get_db, init_db
from src.db.migrations import run_migrations

# Import API routers
from src.dashboard.api import status, positions, control, rates, settings as settings_api
from src.dashboard.api import auth as auth_api, balances as balances_api, events as events_api

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting dashboard API...")
    settings = get_dashboard_settings()
    
    # Initialize database
    logger.info("Initializing database...")
    db = await init_db()
    
    # Run migrations
    logger.info("Running database migrations...")
    try:
        version = await run_migrations(db)
        logger.info(f"Database schema version: {version}")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    
    # Initialize event manager for SSE
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
    
    yield
    
    # Shutdown
    logger.info("Shutting down dashboard...")
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
    
    await db.close()
    logger.info("Dashboard stopped")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_dashboard_settings()
    
    app = FastAPI(
        title="Delta Neutral Bot API",
        description="API backend for Delta Neutral Bot React frontend",
        version="0.2.0",
        lifespan=lifespan,
    )
    
    # Security headers middleware
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
    
    # CORS middleware - allow React dev server and production
    allowed_origins = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Common React port
        "http://127.0.0.1:5173",
    ]
    if settings.dashboard_env == "development":
        allowed_origins.append("*")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Include API routers
    app.include_router(status.router, prefix="/api/v1")
    app.include_router(positions.router, prefix="/api/v1")
    app.include_router(control.router, prefix="/api/v1")
    app.include_router(rates.router, prefix="/api/v1")
    app.include_router(settings_api.router, prefix="/api/v1")
    app.include_router(auth_api.router, prefix="/api/v1")
    app.include_router(balances_api.router, prefix="/api/v1")
    app.include_router(events_api.router, prefix="/api/v1")
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        bridge = get_bot_bridge()
        bot_healthy = False
        
        if bridge:
            try:
                bot_healthy = await bridge.health_check()
            except Exception:
                pass
        
        db = get_db()
        db_healthy = False
        try:
            await db.execute("SELECT 1")
            db_healthy = True
        except Exception:
            pass
        
        return {
            "status": "healthy" if db_healthy else "unhealthy",
            "bot_connected": bot_healthy,
            "database": "healthy" if db_healthy else "error",
        }
    
    # Serve React frontend static files
    frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
    
    if os.path.exists(frontend_dist):
        # Serve static files
        app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")
        
        # Serve root static files (favicon, etc.)
        for item in os.listdir(frontend_dist):
            if item != "assets":
                item_path = os.path.join(frontend_dist, item)
                if os.path.isfile(item_path):
                    app.mount(f"/{item}", StaticFiles(directory=frontend_dist), name=item)
        
        # Catch-all route: serve index.html for all non-API routes (SPA behavior)
        @app.get("/{path:path}")
        async def serve_spa(path: str):
            """Serve React SPA index.html for all routes (client-side routing)."""
            # Don't catch API routes
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            
            index_path = os.path.join(frontend_dist, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            else:
                return JSONResponse(
                    {"error": "Frontend not built. Run 'npm run build' in frontend/"},
                    status_code=500
                )
    else:
        # Frontend not built yet - show helpful message
        @app.get("/")
        async def root():
            return {
                "message": "Delta Neutral Bot API",
                "status": "Frontend not built",
                "instructions": "Run 'cd frontend && npm run build' to build the React app",
                "api_docs": "/docs",
            }
    
    return app


# Create the app instance
app = create_app()
