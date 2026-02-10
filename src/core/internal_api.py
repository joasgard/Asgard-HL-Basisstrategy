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


@internal_app.post("/internal/positions/open")
async def open_position_internal(
    request: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Open a new delta-neutral position.
    
    This is a synchronous endpoint that executes the full position opening
    flow. The dashboard should call this via the async job pattern.
    
    Request body:
    {
        "asset": "SOL",
        "leverage": 3.0,
        "size_usd": 10000,
        "protocol": "kamino"  // optional, auto-selected if not provided
    }
    """
    verify_internal_token(credentials)
    bot = get_bot()
    
    try:
        from decimal import Decimal
        from src.models.common import Asset
        from src.venues.asgard.market_data import AsgardMarketData
        
        # Parse request
        asset_str = request.get("asset", "SOL")
        leverage = Decimal(str(request.get("leverage", 3.0)))
        size_usd = Decimal(str(request.get("size_usd", 10000)))
        protocol_override = request.get("protocol")
        
        asset = Asset(asset_str)
        
        # Get market data for protocol selection
        market_data = AsgardMarketData()
        
        # Select protocol (auto or override)
        if protocol_override:
            from src.models.common import Protocol
            selected_protocol = Protocol[protocol_override.upper()]
        else:
            # Auto-select best protocol
            protocol_result = await market_data.select_best_protocol(
                asset=asset,
                size_usd=size_usd,
                leverage=leverage
            )
            selected_protocol = protocol_result.protocol
        
        # Build opportunity
        from src.models.opportunity import ArbitrageOpportunity, ProtocolRate
        from src.venues.hyperliquid.funding_oracle import HyperliquidFundingOracle
        
        # Get Hyperliquid funding rate
        oracle = HyperliquidFundingOracle()
        funding_rates = await oracle.get_current_funding_rates()
        sol_funding = funding_rates.get("SOL")
        
        if not sol_funding:
            return {
                "success": False,
                "error": "Failed to get Hyperliquid funding rate",
                "stage": "market_data"
            }
        
        # Get Asgard rates for selected protocol
        markets = await market_data.get_markets()
        protocol_rate = None
        
        for strategy_name, strategy_data in markets.get("strategies", {}).items():
            if asset.value in strategy_name:
                for source in strategy_data.get("liquiditySources", []):
                    if source.get("lendingProtocol") == selected_protocol.value:
                        from src.config.assets import ASSETS
                        metadata = ASSETS[asset]
                        
                        lending_apy = source.get("tokenALendingApyRate", 0)
                        borrowing_apy = source.get("tokenBBorrowingApyRate", 0)
                        staking_apy = metadata.staking_apy if metadata.is_lst else 0
                        
                        net_carry_apy = (lending_apy + staking_apy - borrowing_apy * (leverage - 1))
                        
                        protocol_rate = ProtocolRate(
                            protocol=selected_protocol,
                            token_a_apy=lending_apy + staking_apy,
                            token_b_apy=borrowing_apy,
                            net_carry_apr=net_carry_apy,
                            max_leverage=source.get("longMaxLeverage", 4.0),
                            capacity_usd=float(source.get("tokenAMaxDepositCapacity", "1000000"))
                        )
                        break
                if protocol_rate:
                    break
        
        if not protocol_rate:
            return {
                "success": False,
                "error": f"No valid rate found for {asset.value} on {selected_protocol.name}",
                "stage": "market_data"
            }
        
        # Create opportunity
        opportunity = ArbitrageOpportunity(
            asset=asset,
            selected_protocol=selected_protocol,
            asgard_rate=protocol_rate,
            hyperliquid_rate=sol_funding,
            leverage=leverage,
            deployed_capital_usd=size_usd * 2,  # Total capital (both sides)
            position_size_usd=size_usd,
            hyperliquid_funding_premium_8hr=sol_funding.funding_rate,
            expected_total_apr=0,  # Will be calculated
            volatility_30d=0.1,  # Placeholder
            preflight_checks_passed=False,  # Will run preflight
        )
        
        # Run preflight checks
        preflight_result = await bot._position_manager.run_preflight_checks(opportunity)
        
        if not preflight_result.passed:
            return {
                "success": False,
                "error": "Preflight checks failed",
                "stage": "preflight",
                "failed_checks": {
                    name: str(result) for name, result in preflight_result.checks.items() 
                    if not result
                }
            }
        
        # Mark preflight as passed
        opportunity.preflight_checks_passed = True
        
        # Execute position opening
        result = await bot._position_manager.open_position(opportunity)
        
        if result.success:
            return {
                "success": True,
                "position_id": result.position.position_id,
                "asgard_pda": result.position.asgard.position_pda if hasattr(result.position.asgard, 'position_pda') else None,
                "selected_protocol": selected_protocol.name,
                "hyperliquid_funding_rate": float(sol_funding.funding_rate)
            }
        else:
            # Check if partial failure (Asgard opened but Hyperliquid failed)
            partial = {
                "asgard_opened": result.stage != "asgard_open" if hasattr(result, 'stage') else False,
                "stage": result.stage if hasattr(result, 'stage') else "unknown",
                "unwind_attempted": True  # PositionManager tries to unwind on failure
            }
            
            return {
                "success": False,
                "error": result.error,
                "stage": result.stage if hasattr(result, 'stage') else "unknown",
                "partial_result": partial
            }
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to open position: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "stage": "unknown"
        }


@internal_app.post("/internal/positions/{position_id}/close")
async def close_position_internal(
    position_id: str,
    request: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Close a delta-neutral position.
    
    Request body:
    {
        "reason": "manual"  // optional, default: "manual"
    }
    
    Returns:
    {
        "success": true/false,
        "position_id": "...",
        "error": "..."  // only if failed
    }
    """
    verify_internal_token(credentials)
    bot = get_bot()
    
    try:
        from src.models.position import ExitReason
        
        reason_str = request.get("reason", "manual")
        try:
            reason = ExitReason(reason_str)
        except ValueError:
            reason = ExitReason.MANUAL
        
        result = await bot._position_manager.close_position(position_id, reason)
        
        if result.success:
            return {
                "success": True,
                "position_id": position_id,
                "closed_at": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "position_id": position_id,
                "error": result.error
            }
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to close position {position_id}: {e}", exc_info=True)
        return {
            "success": False,
            "position_id": position_id,
            "error": str(e)
        }


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
