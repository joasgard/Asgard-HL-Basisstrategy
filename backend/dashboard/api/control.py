"""Control API endpoints (pause, resume, emergency stop)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.dashboard.auth import require_operator, require_admin, get_current_user
from backend.dashboard.config import get_dashboard_settings
from backend.dashboard.dependencies import get_bot_bridge, require_bot_bridge
from shared.common.schemas import User, ControlResponse

router = APIRouter(tags=["control"])


class PauseRequest(BaseModel):
    """Pause request body."""
    reason: str
    scope: str = "all"  # all, entry, exit, asgard, hyperliquid


class ResumeRequest(BaseModel):
    """Resume request body."""
    pass  # No fields needed for resume


@router.post("/pause", response_model=ControlResponse)
async def pause_bot(
    request: PauseRequest,
    user: User = Depends(require_operator)
):
    """
    Pause bot operations.
    Requires operator role or higher.
    
    Scopes:
    - all: Pause all operations
    - entry: Pause new position entry only
    - exit: Pause position exit only
    - asgard: Pause Asgard (Solana) operations only
    - hyperliquid: Pause Hyperliquid (Arbitrum) operations only
    """
    bot_bridge = require_bot_bridge()
    settings = get_dashboard_settings()
    
    try:
        success = await bot_bridge.pause(
            api_key=settings.bot_admin_key,
            reason=f"{request.reason} (by {user.user_id})",
            scope=request.scope
        )
        
        return ControlResponse(
            success=success,
            message="Bot paused successfully" if success else "Failed to pause bot"
        )
    except Exception as e:
        raise HTTPException(503, f"Bot unavailable: {e}")


@router.post("/resume", response_model=ControlResponse)
async def resume_bot(
    request: ResumeRequest,
    user: User = Depends(require_operator)
):
    """
    Resume bot operations.
    Requires operator role or higher.
    """
    bot_bridge = require_bot_bridge()
    settings = get_dashboard_settings()
    
    try:
        success = await bot_bridge.resume(
            api_key=settings.bot_admin_key
        )
        
        return ControlResponse(
            success=success,
            message="Bot resumed successfully" if success else "Failed to resume bot"
        )
    except Exception as e:
        raise HTTPException(503, f"Bot unavailable: {e}")


@router.post("/emergency-stop", response_model=ControlResponse)
async def emergency_stop(user: User = Depends(require_admin)):
    """
    Emergency stop - pause all operations immediately.
    Requires admin role.
    
    This is a more severe action that also triggers alerts.
    """
    bot_bridge = require_bot_bridge()
    settings = get_dashboard_settings()
    
    try:
        # TODO: Trigger emergency alerts
        
        success = await bot_bridge.pause(
            api_key=settings.bot_admin_key,
            reason=f"EMERGENCY STOP triggered by {user.user_id}",
            scope="all"
        )
        
        return ControlResponse(
            success=success,
            message="Emergency stop activated" if success else "Failed to activate emergency stop"
        )
    except Exception as e:
        raise HTTPException(503, f"Bot unavailable: {e}")
