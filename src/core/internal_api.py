"""
Internal HTTP API for dashboard communication.
Runs on localhost:8000, NOT exposed externally.
"""

from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, Depends, HTTPException, status, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.shared.schemas import BotStats, PositionSummary, PositionDetail, PauseState, PauseScope
from src.core.pause_controller import PauseScope as CorePauseScope
from src.config.settings import get_settings

security = HTTPBearer()
internal_app = FastAPI(title="Bot Internal API")

# Reference to bot instance (set during startup)
_bot_instance = None


def set_bot_instance(bot):
    """Set the bot instance for the internal API."""
    global _bot_instance
    _bot_instance = bot


def get_bot():
    """Get the bot instance or raise 503."""
    if _bot_instance is None:
        raise HTTPException(503, "Bot not initialized")
    return _bot_instance


def verify_internal_token(credentials: HTTPAuthorizationCredentials):
    """Verify the internal API token (different from admin_api_key)."""
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
    
    scope_map = {
        "all": CorePauseScope.ALL,
        "entry": CorePauseScope.ENTRY,
        "exit": CorePauseScope.EXIT,
        "asgard": CorePauseScope.ASGARD,
        "hyperliquid": CorePauseScope.HYPERLIQUID,
    }
    
    scope = scope_map.get(request.get("scope", "all"), CorePauseScope.ALL)
    
    # Bot validates api_key internally
    result = await bot.pause(
        api_key=request["api_key"],
        reason=request["reason"],
        scope=scope
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
    await websocket.send_json({"type": "connected", "message": "WebSocket events not yet implemented"})
    await websocket.close()


def _position_to_summary(position) -> PositionSummary:
    """Convert CombinedPosition to PositionSummary."""
    from decimal import Decimal
    
    opened_at = position.created_at if hasattr(position, 'created_at') else datetime.utcnow()
    hold_duration_hours = (datetime.utcnow() - opened_at).total_seconds() / 3600
    
    return PositionSummary(
        position_id=position.position_id,
        asset=position.asgard.asset.value if hasattr(position.asgard.asset, 'value') else str(position.asgard.asset),
        status=position.status,
        leverage=position.asgard.leverage,
        deployed_usd=position.asgard.collateral_usd,
        long_value_usd=position.asgard.current_value_usd,
        short_value_usd=position.hyperliquid.size_usd,
        delta=position.delta,
        delta_ratio=position.delta_ratio,
        asgard_hf=position.asgard.current_health_factor,
        hyperliquid_mf=position.hyperliquid.margin_fraction or Decimal("0"),
        total_pnl_usd=position.total_pnl,
        funding_pnl_usd=position.net_funding_pnl,
        opened_at=opened_at,
        hold_duration_hours=hold_duration_hours
    )


def _position_to_detail(position) -> PositionDetail:
    """Convert CombinedPosition to PositionDetail."""
    from decimal import Decimal
    
    summary = _position_to_summary(position)
    
    distance_to_liq = None
    if position.hyperliquid.margin_fraction is not None and position.hyperliquid.margin_fraction > 0:
        distance_to_liq = Decimal("1") / position.hyperliquid.margin_fraction
    
    return PositionDetail(
        **summary.model_dump(),
        sizing={
            "deployed_usd": position.asgard.collateral_usd,
            "position_size_usd": getattr(position.asgard, 'position_size_usd', position.asgard.collateral_usd),
            "collateral_usd": position.asgard.collateral_usd,
            "borrowed_usd": getattr(position.asgard, 'token_b_borrowed', Decimal("0"))
        },
        asgard={
            "position_pda": getattr(position.asgard, 'position_pda', None),
            "collateral_usd": position.asgard.collateral_usd,
            "token_a_amount": getattr(position.asgard, 'token_a_amount', Decimal("0")),
            "entry_price": getattr(position.asgard, 'entry_price_token_a', Decimal("0")),
            "current_price": getattr(position.asgard, 'current_token_a_price', Decimal("0")),
            "current_health_factor": position.asgard.current_health_factor
        },
        hyperliquid={
            "size_sol": position.hyperliquid.size_sol,
            "entry_px": position.hyperliquid.entry_px,
            "mark_px": position.hyperliquid.mark_px,
            "leverage": position.hyperliquid.leverage,
            "margin_used": position.hyperliquid.margin_used,
            "margin_fraction": position.hyperliquid.margin_fraction or Decimal("0")
        },
        pnl={
            "long_pnl": position.asgard.pnl_usd,
            "short_pnl": position.hyperliquid.unrealized_pnl,
            "position_pnl": position.asgard.pnl_usd + position.hyperliquid.unrealized_pnl,
            "funding_pnl": position.net_funding_pnl,
            "total_pnl": position.total_pnl,
            "total_pnl_pct": position.total_pnl / position.asgard.collateral_usd if position.asgard.collateral_usd else Decimal("0")
        },
        risk={
            "delta": position.delta,
            "delta_ratio": position.delta_ratio,
            "health_status": "healthy" if not position.is_at_risk else "at_risk",
            "distance_to_liquidation": min(
                position.asgard.current_health_factor,
                distance_to_liq or Decimal("1")
            )
        }
    )
