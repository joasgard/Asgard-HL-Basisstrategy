"""Rates API endpoints for fetching Asgard and Hyperliquid rates."""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any
import logging

from src.venues.asgard.client import AsgardClient
from src.venues.hyperliquid.funding_oracle import HyperliquidFundingOracle
from src.config.assets import Asset, ASSETS

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rates"])


@router.get("/rates")
async def get_rates(
    leverage: float = Query(3.0, ge=2.0, le=4.0, description="Desired leverage multiplier")
) -> Dict[str, Any]:
    """
    Get current rates for Asgard and Hyperliquid at specified leverage.
    
    No API keys required - uses public endpoints:
    - Asgard: 1 req/sec public access
    - Hyperliquid: Public funding rates
    
    Returns:
        {
            "asgard": {
                "sol": {"kamino": 12.5, "drift": 11.8, ...},
                "jitosol": {"kamino": 18.2, ...},
                ...
            },
            "hyperliquid": {
                "funding_rate": -0.0025,
                "predicted": -0.0030,
                "annualized": -21.9
            }
        }
    """
    try:
        # Fetch Asgard rates (no API key needed for public access)
        asgard_rates = await _fetch_asgard_rates(leverage)
        
        # Fetch Hyperliquid funding rates (public)
        hl_rates = await _fetch_hyperliquid_rates(leverage)
        
        return {
            "asgard": asgard_rates,
            "hyperliquid": hl_rates,
            "leverage": leverage,
        }
        
    except Exception as e:
        logger.error(f"Error fetching rates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_asgard_rates(leverage: float) -> Dict[str, Dict[str, float]]:
    """Fetch Asgard market rates at specified leverage."""
    asgard_rates: Dict[str, Dict[str, float]] = {}
    
    try:
        async with AsgardClient() as client:
            markets = await client.get_markets()
            
            for asset in [Asset.SOL, Asset.JITOSOL, Asset.JUPSOL, Asset.INF]:
                asset_key = asset.value.lower()
                asgard_rates[asset_key] = {}
                
                # Get asset metadata for staking APY
                metadata = ASSETS[asset]
                
                # Find markets for this asset
                for strategy_name, strategy_data in markets.get("strategies", {}).items():
                    if asset.value in strategy_name or (asset == Asset.SOL and strategy_name == "SOL"):
                        for source in strategy_data.get("liquiditySources", []):
                            protocol = source.get("lendingProtocol")
                            protocol_name = {0: "marginfi", 1: "kamino", 2: "solend", 3: "drift"}.get(protocol)
                            
                            if not protocol_name:
                                continue
                            
                            # Calculate net APY at requested leverage
                            lending_apy = source.get("tokenALendingApyRate", 0)
                            borrowing_apy = source.get("tokenBBorrowingApyRate", 0)
                            
                            # Net APY = (Lending + Staking) - Borrowing * (leverage - 1)
                            staking_yield = metadata.staking_apy if metadata.is_lst else 0
                            net_apy = (lending_apy + staking_yield - borrowing_apy * (leverage - 1)) * 100
                            
                            asgard_rates[asset_key][protocol_name] = round(net_apy, 2)
                            
        logger.info(f"Fetched Asgard rates for {len(asgard_rates)} assets")
        
    except Exception as e:
        logger.error(f"Failed to fetch Asgard rates: {e}")
        # Return empty dict - frontend will show loading/error state
        asgard_rates = {
            "sol": {},
            "jitosol": {},
            "jupsol": {},
            "inf": {},
        }
    
    return asgard_rates


async def _fetch_hyperliquid_rates(leverage: float) -> Dict[str, float]:
    """Fetch Hyperliquid funding rates at specified leverage."""
    try:
        async with HyperliquidFundingOracle() as oracle:
            # Get current funding rates for all coins
            funding_rates = await oracle.get_current_funding_rates()
            
            # Get SOL funding rate
            sol_rate = funding_rates.get("SOL")
            if sol_rate:
                # Scale by leverage
                return {
                    "funding_rate": round(sol_rate.funding_rate * leverage * 100, 4),
                    "predicted": round(sol_rate.funding_rate * leverage * 100, 4),  # Use current as predicted for now
                    "annualized": round(sol_rate.annualized_rate * leverage * 100, 2),
                }
            else:
                logger.warning("SOL funding rate not found in response")
                return {
                    "funding_rate": 0.0,
                    "predicted": 0.0,
                    "annualized": 0.0,
                }
                
    except Exception as e:
        logger.error(f"Failed to fetch Hyperliquid rates: {e}")
        return {
            "funding_rate": 0.0,
            "predicted": 0.0,
            "annualized": 0.0,
        }


@router.get("/rates/simple")
async def get_simple_rates() -> Dict[str, Any]:
    """Get simplified rates for display without leverage calculation."""
    return await get_rates(leverage=3.0)
