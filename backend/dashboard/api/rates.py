"""Rates API endpoints for fetching Asgard SOL/USDC and Hyperliquid rates."""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any
import logging

from bot.venues.asgard.client import AsgardClient
from bot.venues.hyperliquid.funding_oracle import HyperliquidFundingOracle

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rates"])


@router.get("/rates")
async def get_rates(
    leverage: float = Query(3.0, ge=1.1, le=4.0, description="Desired leverage multiplier (1.1x - 4x)")
) -> Dict[str, Any]:
    """
    Get current rates for SOL/USDC delta-neutral strategy.
    
    Strategy:
    - Long: Deposit SOL on Asgard SOL/USDC, borrow USDC
    - Short: Short SOL-PERP on Hyperliquid to hedge
    
    No API keys required - uses public endpoints:
    - Asgard: 1 req/sec public access
    - Hyperliquid: Public funding rates
    
    Returns:
        {
            "asgard": {
                "kamino": 8.5,
                "drift": 5.2,
                ...
            },
            "hyperliquid": {
                "funding_rate": -0.0025,
                "predicted": -0.0030,
                "annualized": -0.03
            },
            "combined": {
                "kamino": 8.47,
                "drift": 5.17,
                ...
            },
            "leverage": 3.0
        }
    """
    try:
        # Fetch Asgard rates for SOL/USDC
        asgard_rates, asgard_details = await _fetch_asgard_rates(leverage)
        
        # Fetch Hyperliquid funding rates (public)
        hl_rates = await _fetch_hyperliquid_rates(leverage)
        
        # Calculate combined delta-neutral APY
        # Asgard: Positive = you earn on long SOL position
        # Hyperliquid: Negative funding = shorts get paid (positive return for short)
        # Combined = Asgard Net APY - Hyperliquid Annualized Rate
        # (We subtract because negative funding is good for shorts)
        hl_annualized = hl_rates.get("annualized", 0)
        combined_rates = {
            protocol: round(apy - hl_annualized, 2)  # Subtract: negative funding = +return
            for protocol, apy in asgard_rates.items()
        }
        
        # Find best protocol details for UI
        best_protocol = max(combined_rates, key=combined_rates.get) if combined_rates else None
        best_asgard_details = asgard_details.get(best_protocol) if best_protocol else None
        
        return {
            "asgard": asgard_rates,
            "asgard_details": best_asgard_details,
            "hyperliquid": hl_rates,
            "combined": combined_rates,
            "leverage": leverage,
        }
        
    except Exception as e:
        logger.error(f"Error fetching rates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch rates")


async def _fetch_asgard_rates(leverage: float) -> tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
    """
    Fetch Asgard SOL/USDC market rates at specified leverage.
    
    For SOL/USDC delta-neutral:
    - Deposit SOL (Token A) → earn lending APY
    - Borrow USDC (Token B) → pay borrowing APY
    - Net APY = Lending - Borrowing * (leverage - 1)
    
    Returns:
        Tuple of (rates dict, details dict with lending/borrowing breakdown)
    """
    asgard_rates: Dict[str, float] = {}
    asgard_details: Dict[str, Dict[str, float]] = {}
    
    try:
        async with AsgardClient() as client:
            markets = await client.get_markets()
            
            # Only support SOL/USDC strategy
            if "SOL/USDC" not in markets.get("strategies", {}):
                logger.warning("SOL/USDC strategy not found in Asgard markets")
                return {}, {}
            
            strategy_data = markets["strategies"]["SOL/USDC"]
            
            for source in strategy_data.get("liquiditySources", []):
                protocol = source.get("lendingProtocol")
                protocol_name = {0: "marginfi", 1: "kamino", 2: "solend", 3: "drift"}.get(protocol)
                
                if not protocol_name:
                    continue
                
                # Get raw rates (API returns decimals, e.g., 0.05 = 5%)
                lending_apy = source.get("tokenALendingApyRate", 0)
                borrowing_apy = source.get("tokenBBorrowingApyRate", 0)
                
                # For delta-neutral SOL/USDC:
                # - Earn: Lending APY on SOL * leverage (collateral + borrowed amount)
                # - Pay: Borrowing APY on USDC * (leverage - 1)
                # Net APY = (Lending * leverage) - (Borrowing * (leverage - 1))
                #
                # Example at 3x leverage with $1000 collateral:
                # - Deposit $1000 SOL, borrow $2000 USDC, swap to SOL
                # - Total lent: $3000 SOL earning lending_apy
                # - Total borrowed: $2000 USDC paying borrowing_apy
                # - Net = (0.04 * 3) - (0.05 * 2) = 0.12 - 0.10 = +2%
                net_apy_decimal = (lending_apy * leverage) - (borrowing_apy * (leverage - 1))
                
                # Convert to percentage for display
                asgard_rates[protocol_name] = round(net_apy_decimal * 100, 2)
                
                # Store detailed breakdown for the best protocol
                asgard_details[protocol_name] = {
                    "base_lending_apy": round(lending_apy * 100, 2),
                    "lending_apy": round(lending_apy * leverage * 100, 2),
                    "base_borrowing_apy": round(borrowing_apy * 100, 2),
                    "borrowing_apy": round(borrowing_apy * (leverage - 1) * 100, 2),
                    "net_apy": round(net_apy_decimal * 100, 2),
                }
                
                logger.debug(
                    f"SOL/USDC {protocol_name}: lend={lending_apy*100:.2f}%, "
                    f"borrow={borrowing_apy*100:.2f}%, net={net_apy_decimal*100:.2f}% @ {leverage}x"
                )
                        
        logger.info(f"Fetched Asgard SOL/USDC rates: {asgard_rates}")
        
    except Exception as e:
        logger.error(f"Failed to fetch Asgard rates: {e}")
    
    return asgard_rates, asgard_details


async def _fetch_hyperliquid_rates(leverage: float) -> Dict[str, float]:
    """Fetch Hyperliquid SOL-PERP funding rates at specified leverage."""
    try:
        async with HyperliquidFundingOracle() as oracle:
            # Get current funding rates for all coins
            funding_rates = await oracle.get_current_funding_rates()
            
            # Get SOL funding rate
            sol_rate = funding_rates.get("SOL")
            if sol_rate:
                # Scale by leverage
                # funding_rate is hourly (e.g., -0.000007 = -0.0007%)
                # annualized_rate is already calculated (hourly * 24 * 365)
                return {
                    "funding_rate": round(sol_rate.funding_rate * 100, 6),  # Hourly %
                    "predicted": round(sol_rate.funding_rate * 100, 6),  # Use current as predicted
                    "base_annualized": round(sol_rate.annualized_rate * 100, 2),  # Annualized % (no leverage)
                    "annualized": round(sol_rate.annualized_rate * leverage * 100, 2),  # Annualized % at leverage
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
