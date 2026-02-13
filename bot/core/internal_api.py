"""
Internal HTTP API for dashboard communication.
Runs on localhost:8000, NOT exposed externally.
"""

from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, Depends, HTTPException, status, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from shared.common.schemas import BotStats, PositionSummary, PositionDetail, PauseState, PauseScope
from bot.core.pause_controller import PauseScope as CorePauseScope
from shared.config.settings import get_settings

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


def _get_server_secret() -> str:
    """Load server secret from file."""
    from shared.config.settings import SECRETS_DIR
    secret_path = SECRETS_DIR / "server_secret.txt"
    if not secret_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server secret not configured"
        )
    return secret_path.read_text().strip()


def verify_internal_token(credentials: HTTPAuthorizationCredentials) -> str:
    """Verify the internal API token.

    Accepts either:
    - JWT (HS256): extracts and returns user_id from ``sub`` claim
    - Raw bearer token (legacy): returns empty string (no user scoping)

    Returns:
        user_id from JWT, or "" for legacy token auth.
    """
    secret = _get_server_secret()
    token = credentials.credentials

    # Try JWT first (has dots)
    if "." in token:
        try:
            from shared.auth.internal_jwt import verify_internal_jwt
            user_id = verify_internal_jwt(token, secret)
            if user_id:
                return user_id
        except Exception:
            pass

    # Fallback: raw bearer token (legacy)
    if token == secret:
        return ""

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid internal token"
    )


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


@internal_app.get("/health/wallets")
async def health_wallets(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Per-user server wallet health: addresses, balances, signing metrics."""
    verify_internal_token(credentials)

    from shared.db.database import Database
    from bot.venues.privy_signer import get_signing_metrics

    db = Database()
    try:
        await db.connect()
        rows = await db.fetchall(
            """SELECT id, server_evm_address, server_solana_address,
                      server_evm_wallet_id, server_solana_wallet_id
               FROM users
               WHERE server_evm_wallet_id IS NOT NULL
                  OR server_solana_wallet_id IS NOT NULL"""
        )
    finally:
        await db.close()

    users = []
    for row in rows:
        users.append({
            "user_id": row["id"],
            "evm_address": row["server_evm_address"],
            "solana_address": row["server_solana_address"],
            "evm_wallet_id": row["server_evm_wallet_id"],
            "solana_wallet_id": row["server_solana_wallet_id"],
        })

    metrics = get_signing_metrics()
    return {
        "users": users,
        "signing_metrics": {
            "total_last_hour": metrics.total_last_hour,
            "policy_violations_24h": metrics.policy_violations_24h,
            "breakdown_1h": metrics.get_summary(3600),
            "breakdown_24h": metrics.get_summary(86400),
        },
        "circuit_breaker": {
            "is_open": _get_circuit_breaker_status(),
        },
    }


def _get_circuit_breaker_status() -> bool:
    """Check if the signing circuit breaker is currently open."""
    from bot.venues.privy_signer import _circuit_breaker
    return _circuit_breaker.is_open


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
    """Get positions, scoped to the authenticated user if JWT is used."""
    auth_user_id = verify_internal_token(credentials)
    bot = get_bot()

    positions = bot.get_positions()

    # N5: If authenticated via JWT, only return the requesting user's positions
    if auth_user_id:
        positions = {
            pos_id: pos for pos_id, pos in positions.items()
            if getattr(pos, "user_id", None) == auth_user_id
        }

    return {
        pos_id: _position_to_summary(pos).model_dump(mode="json")
        for pos_id, pos in positions.items()
    }


@internal_app.get("/internal/positions/{position_id}", response_model=PositionDetail)
async def get_position_detail(
    position_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get single position detail, scoped to authenticated user."""
    auth_user_id = verify_internal_token(credentials)
    bot = get_bot()

    position = bot.get_positions().get(position_id)
    if not position:
        raise HTTPException(404, "Position not found")

    # N5: If authenticated via JWT, verify ownership
    if auth_user_id and getattr(position, "user_id", None) != auth_user_id:
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
        from shared.models.common import Asset
        from bot.venues.asgard.market_data import AsgardMarketData
        
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
            from shared.models.common import Protocol
            selected_protocol = Protocol[protocol_override.upper()]
        else:
            # Auto-select best protocol
            protocol_result = await market_data.select_best_protocol(
                asset=asset,
                size_usd=float(size_usd),
                leverage=float(leverage),
            )
            selected_protocol = protocol_result.protocol
        
        # Build opportunity using actual models
        from uuid import uuid4
        from shared.models.opportunity import ArbitrageOpportunity, OpportunityScore
        from shared.models.funding import FundingRate as ModelFundingRate, AsgardRates
        from shared.config.assets import get_mint
        from bot.venues.hyperliquid.funding_oracle import HyperliquidFundingOracle

        # Get Hyperliquid funding rate
        oracle = HyperliquidFundingOracle()
        try:
            funding_rates = await oracle.get_current_funding_rates()
            sol_funding = funding_rates.get("SOL")
        finally:
            await oracle.client.close()

        if not sol_funding:
            return {
                "success": False,
                "error": "Failed to get Hyperliquid funding rate",
                "stage": "market_data"
            }

        # Build model FundingRate from oracle rate (oracle rate_8hr is hourly * 8)
        current_funding = ModelFundingRate(
            timestamp=datetime.utcnow(),
            coin="SOL",
            rate_8hr=Decimal(str(sol_funding.rate_8hr)),
        )

        # Build AsgardRates from protocol_result with real capacity
        token_a_mint = get_mint(asset)
        # Get actual borrow capacity from rates data
        borrow_rates = await market_data.get_borrowing_rates(token_a_mint)
        borrow_capacity = Decimal("0")
        for rate in borrow_rates:
            if rate.protocol == protocol_result.protocol:
                borrow_capacity = Decimal(str(rate.max_borrow_capacity))
                break
        asgard_rates = AsgardRates(
            protocol_id=protocol_result.protocol.value,
            token_a_mint=token_a_mint,
            token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            token_a_lending_apy=Decimal(str(protocol_result.lending_rate)),
            token_b_borrowing_apy=Decimal(str(protocol_result.borrowing_rate)),
            token_b_max_borrow_capacity=borrow_capacity,
        )

        # Calculate score components
        funding_apy = abs(current_funding.rate_annual) * leverage
        net_carry_apy = Decimal(str(protocol_result.net_carry_apy))

        score = OpportunityScore(
            funding_apy=funding_apy,
            net_carry_apy=net_carry_apy,
            lst_staking_apy=Decimal("0"),
        )

        position_size_usd = size_usd * leverage

        # Create opportunity
        opportunity = ArbitrageOpportunity(
            id=str(uuid4()),
            asset=asset,
            selected_protocol=protocol_result.protocol,
            asgard_rates=asgard_rates,
            hyperliquid_coin="SOL",
            current_funding=current_funding,
            predicted_funding=None,
            funding_volatility=Decimal("0"),  # Not checked for manual deploy
            leverage=leverage,
            deployed_capital_usd=size_usd,
            position_size_usd=position_size_usd,
            score=score,
            price_deviation=Decimal("0"),
            preflight_checks_passed=False,
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
                "selected_protocol": protocol_result.protocol.name,
                "hyperliquid_funding_rate": float(sol_funding.rate_8hr)
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
        from shared.models.position import ExitReason
        
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
