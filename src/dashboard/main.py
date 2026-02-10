"""
Delta Neutral Bot Dashboard - FastAPI application.

Web-based control center for the delta neutral trading bot with:
- Setup wizard for initial configuration
- Real-time monitoring dashboard
- Bot control APIs
- Backup and restore
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from src.dashboard.config import get_dashboard_settings
from src.dashboard.bot_bridge import BotBridge
from src.dashboard.dependencies import set_bot_bridge, get_bot_bridge
from src.dashboard.events_manager import event_manager
from src.dashboard.auth import session_manager
from src.db.database import get_db, init_db
from src.db.migrations import run_migrations

# Import API routers
from src.dashboard.api import status, positions, control, rates, settings as settings_api
from src.dashboard.api import setup as setup_api, auth as auth_api, balances as balances_api, events as events_api

logger = logging.getLogger(__name__)

# Templates - use absolute path for reliability
_templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_templates_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting dashboard...")
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
    
    # Set database for session manager
    session_manager.set_db(db)
    
    # Initialize event manager for SSE
    logger.info("Initializing event manager...")
    await event_manager.start()
    
    # Check if setup is complete
    setup_complete = await db.get_config("setup_completed")
    is_setup_complete = setup_complete == "true"
    
    if is_setup_complete:
        logger.info("Setup complete - initializing bot bridge...")
        # Initialize bot bridge
        bot_bridge = BotBridge(
            bot_api_url=settings.bot_api_url,
            internal_token=settings.internal_token
        )
        await bot_bridge.start()
        set_bot_bridge(bot_bridge)
        logger.info(f"Connected to bot at {settings.bot_api_url}")
    else:
        logger.info("Setup not complete - bot bridge will start after setup")
    
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
        title="Delta Neutral Bot Dashboard",
        description="Control Center for Delta Neutral Funding Rate Arbitrage Bot",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # Security headers middleware
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
    
    # CORS middleware - restrictive for security
    allowed_origins = ["http://localhost:8080", "http://127.0.0.1:8080"]
    if settings.dashboard_env == "development":
        allowed_origins.append("*")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    
    # Include API routers
    app.include_router(status.router, prefix="/api/v1")
    app.include_router(positions.router, prefix="/api/v1")
    app.include_router(control.router, prefix="/api/v1")
    app.include_router(rates.router, prefix="/api/v1")
    app.include_router(settings_api.router, prefix="/api/v1")
    app.include_router(auth_api.router)  # Auth routes
    app.include_router(balances_api.router, prefix="/api/v1")  # Balances routes
    app.include_router(events_api.router, prefix="/api/v1")  # Events/SSE routes
    app.include_router(setup_api.router)  # Setup routes (no prefix for /setup paths)
    
    # Health check endpoint (JSON API)
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
    
    # Setup middleware - redirect to setup if not complete
    @app.middleware("http")
    async def setup_redirect(request: Request, call_next):
        """Redirect to setup wizard if setup not complete."""
        # Skip API routes and static files
        path = request.url.path
        if path.startswith("/api/") or path.startswith("/static/"):
            return await call_next(request)
        
        if path in ["/health", "/setup", "/login"] or path.startswith("/setup/"):
            return await call_next(request)
        
        # Check setup status
        try:
            db = get_db()
            setup_complete = await db.get_config("setup_completed")
            if setup_complete != "true" and not path.startswith("/setup"):
                return RedirectResponse(url="/setup")
        except Exception:
            # Database not ready, allow through
            pass
        
        return await call_next(request)
    
    # Template routes (HTML pages)
    @app.get("/")
    async def dashboard_page(request: Request):
        """Render main dashboard page with default context."""
        # Provide default values for template variables
        context = {
            "request": request,
            "positions_count": 0,
            "pnl_24h": 0.0,
            "total_value": 0.0,
            "user": None,
            "bot_connected": False,
            "current_funding": {},
            "risk_preset": "balanced",
            "max_position_size": 1000,
            "leverage": 2,
        }
        return templates.TemplateResponse("dashboard.html", context)
    
    @app.get("/positions")
    async def positions_page(request: Request):
        """Render positions page with default context."""
        context = {
            "request": request,
            "positions": [],
            "user": None,
        }
        return templates.TemplateResponse("positions.html", context)
    
    @app.get("/setup")
    async def setup_page(request: Request):
        """Render setup wizard page with current step."""
        from src.dashboard.setup import SetupSteps
        from src.db.database import get_db
        
        db = get_db()
        steps = SetupSteps(db=db)
        state = await steps.get_setup_state()
        
        # 4-step wizard: Auth → Wallets → Exchange → Dashboard
        step_templates = {
            1: "setup/step1_privy_auth.html",  # Step 1: Privy OAuth login
            2: "setup/step2_wallets.html",     # Step 2: Wallet creation
            3: "setup/step3_exchange.html",    # Step 3: Exchange config
        }
        
        # If setup complete (step 4+), redirect to dashboard
        if state.step >= 4:
            return RedirectResponse(url="/dashboard")
        
        template_name = step_templates.get(state.step, "setup/step1_privy_auth.html")
        
        return templates.TemplateResponse(
            request, 
            template_name,
            context={
                "step": state.step,
                "setup_complete": state.step >= 4,
                **state.to_dict()
            }
        )
    
    @app.get("/login")
    async def login_page(request: Request):
        """Render login page."""
        return templates.TemplateResponse(request, "login.html")
    
    @app.get("/dashboard")
    async def dashboard_page(request: Request):
        """Render main dashboard (Step 4)."""
        from src.dashboard.setup import SetupSteps
        from src.db.database import get_db
        
        db = get_db()
        steps = SetupSteps(db=db)
        state = await steps.get_setup_state()
        
        # If not at dashboard step yet, redirect to setup
        if state.step < 4:
            return RedirectResponse(url="/setup")
        
        # Get wallet addresses
        evm_address = await db.get_config("wallet_evm_address")
        solana_address = await db.get_config("wallet_solana_address")
        
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            context={
                "step": 4,
                "evm_address": evm_address,
                "solana_address": solana_address,
                "bot_status": "STANDBY",
                "positions_count": 0,
                "pnl_24h": "$0.00",
            }
        )
    
    @app.get("/dashboard/funding")
    async def funding_page(request: Request):
        """Render funding page."""
        from src.db.database import get_db
        db = get_db()
        
        evm_address = await db.get_config("wallet_evm_address")
        solana_address = await db.get_config("wallet_solana_address")
        
        return templates.TemplateResponse(
            request,
            "funding.html",
            context={
                "evm_address": evm_address,
                "solana_address": solana_address,
            }
        )
    
    @app.get("/dashboard/strategy")
    async def strategy_page(request: Request):
        """Render strategy configuration page."""
        return templates.TemplateResponse(
            request,
            "strategy.html",
            context={}
        )
    
    # Static files - use absolute path
    try:
        _static_dir = os.path.join(os.path.dirname(__file__), "static")
        app.mount("/static", StaticFiles(directory=_static_dir), name="static")
    except RuntimeError:
        logger.warning("Static files directory not found, skipping mount")
    
    return app


# Create application instance for running directly
app = create_app()
