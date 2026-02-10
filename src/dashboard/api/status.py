"""Status and health API endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from src.dashboard.auth import require_viewer
from src.dashboard.dependencies import get_bot_bridge, require_bot_bridge
from src.shared.schemas import User

router = APIRouter(tags=["status"])


@router.get("/health")
async def api_health_check():
    """
    Public health check endpoint.
    Returns dashboard and bot health status.
    """
    try:
        bot_bridge = get_bot_bridge()
        bot_healthy = await bot_bridge.health_check()
    except Exception:
        bot_healthy = False
    
    return {
        "dashboard": {"status": "healthy"},
        "bot": {"status": "healthy" if bot_healthy else "unavailable"},
    }


@router.get("/status")
async def get_status(user: User = Depends(require_viewer)):
    """
    Get detailed bot status.
    Requires viewer role or higher.
    """
    bot_bridge = require_bot_bridge()
    
    try:
        stats = await bot_bridge.get_stats()
        pause_state = await bot_bridge.get_pause_state()
        
        return {
            "bot": {
                "running": True,
                "uptime_seconds": stats.uptime_seconds,
                "uptime_formatted": stats.uptime_formatted,
            },
            "stats": {
                "opportunities_found": stats.opportunities_found,
                "positions_opened": stats.positions_opened,
                "positions_closed": stats.positions_closed,
                "errors_count": stats.errors_count,
            },
            "pause_state": pause_state.model_dump(),
        }
    except Exception as e:
        raise HTTPException(503, f"Bot unavailable: {e}")


@router.get("/stats")
async def get_stats(user: User = Depends(require_viewer)):
    """
    Get bot statistics.
    Requires viewer role or higher.
    """
    bot_bridge = require_bot_bridge()
    
    try:
        stats = await bot_bridge.get_stats()
        return stats.model_dump()
    except Exception as e:
        raise HTTPException(503, f"Bot unavailable: {e}")


@router.get("/pause-state")
async def get_pause_state(user: User = Depends(require_viewer)):
    """
    Get current pause state.
    Requires viewer role or higher.
    """
    bot_bridge = require_bot_bridge()
    
    try:
        state = await bot_bridge.get_pause_state()
        return state.model_dump()
    except Exception as e:
        raise HTTPException(503, f"Bot unavailable: {e}")
