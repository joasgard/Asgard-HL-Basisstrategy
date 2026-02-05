"""Dashboard FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from src.dashboard.config import get_dashboard_settings
from src.dashboard.bot_bridge import BotBridge
from src.dashboard.dependencies import set_bot_bridge, get_bot_bridge
from src.dashboard.api import status, positions, control

logger = logging.getLogger(__name__)

# Templates
templates = Jinja2Templates(directory="src/dashboard/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting dashboard...")
    settings = get_dashboard_settings()
    
    # Initialize bot bridge
    bot_bridge = BotBridge(
        bot_api_url=settings.bot_api_url,
        internal_token=settings.internal_token
    )
    await bot_bridge.start()
    
    # Set global reference
    set_bot_bridge(bot_bridge)
    
    logger.info(f"Dashboard started. Connected to bot at {settings.bot_api_url}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down dashboard...")
    try:
        bridge = get_bot_bridge()
        if bridge:
            await bridge.stop()
    except Exception:
        pass
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
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routers
    app.include_router(status.router, prefix="/api/v1")
    app.include_router(positions.router, prefix="/api/v1")
    app.include_router(control.router, prefix="/api/v1")
    
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
        
        return {
            "status": "healthy",
            "bot_connected": bot_healthy,
        }
    
    # Template routes (HTML pages)
    @app.get("/")
    async def dashboard_page(request: Request):
        """Render main dashboard page."""
        return templates.TemplateResponse(request, "dashboard.html")
    
    @app.get("/positions")
    async def positions_page(request: Request):
        """Render positions page."""
        return templates.TemplateResponse(request, "positions.html")
    
    # Static files
    try:
        app.mount("/static", StaticFiles(directory="src/dashboard/static"), name="static")
    except RuntimeError:
        logger.warning("Static files directory not found, skipping mount")
    
    return app


# Create application instance for running directly
app = create_app()
