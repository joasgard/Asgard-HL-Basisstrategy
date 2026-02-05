"""Positions API endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException

from src.dashboard.auth import require_viewer, get_current_user
from src.dashboard.dependencies import get_bot_bridge, require_bot_bridge
from src.shared.schemas import User, PositionSummary, PositionDetail

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=List[PositionSummary])
async def list_positions(user: User = Depends(require_viewer)):
    """
    List all open positions.
    Requires viewer role or higher.
    """
    bot_bridge = require_bot_bridge()
    
    try:
        positions = await bot_bridge.get_positions()
        return list(positions.values())
    except Exception as e:
        raise HTTPException(503, f"Bot unavailable: {e}")


@router.get("/{position_id}", response_model=PositionDetail)
async def get_position(position_id: str, user: User = Depends(require_viewer)):
    """
    Get detailed information for a specific position.
    Requires viewer role or higher.
    """
    bot_bridge = require_bot_bridge()
    
    try:
        detail = await bot_bridge.get_position_detail(position_id)
        return detail
    except Exception as e:
        if "404" in str(e):
            raise HTTPException(404, "Position not found")
        raise HTTPException(503, f"Bot unavailable: {e}")
