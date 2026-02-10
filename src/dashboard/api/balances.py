"""
Wallet balance API endpoints.

Fetches on-chain balances for Solana and Arbitrum wallets.
"""

from typing import Optional, Dict, Any
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.dashboard.auth import get_current_user, User
from src.db.database import get_db, Database
from src.chain.solana import SolanaClient
from src.chain.arbitrum import ArbitrumClient
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/balances", tags=["balances"])


# Token constants
USDC_MINT_SOLANA = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # Mainnet USDC
USDC_CONTRACT_ARBITRUM = "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8"  # Arbitrum USDC


class TokenBalance(BaseModel):
    """Token balance information."""
    token: str
    symbol: str
    balance: float
    decimals: int
    usd_value: Optional[float] = None


class ChainBalance(BaseModel):
    """Balance information for a chain."""
    address: str
    native_balance: float  # SOL or ETH
    native_symbol: str
    tokens: list[TokenBalance]


class BalancesResponse(BaseModel):
    """Full balances response."""
    solana: Optional[ChainBalance] = None
    arbitrum: Optional[ChainBalance] = None
    total_usd_value: Optional[float] = None
    has_sufficient_funds: bool = False
    min_required_sol: float = 0.05  # Minimum SOL for gas
    min_required_usdc_solana: float = 10.0  # Minimum USDC on Solana
    min_required_usdc_arbitrum: float = 10.0  # Minimum USDC on Arbitrum


async def _get_solana_balances(address: str) -> Optional[ChainBalance]:
    """Fetch Solana balances for an address."""
    try:
        async with SolanaClient() as client:
            # Get SOL balance
            sol_balance = await client.get_balance(address)
            
            # Get USDC balance
            usdc_balance = await client.get_token_balance(USDC_MINT_SOLANA, address)
            
            return ChainBalance(
                address=address,
                native_balance=sol_balance,
                native_symbol="SOL",
                tokens=[
                    TokenBalance(
                        token=USDC_MINT_SOLANA,
                        symbol="USDC",
                        balance=usdc_balance,
                        decimals=6,
                        usd_value=usdc_balance  # 1 USDC = $1
                    )
                ]
            )
    except Exception as e:
        logger.error(f"Failed to fetch Solana balances: {e}")
        return None


async def _get_arbitrum_balances(address: str) -> Optional[ChainBalance]:
    """Fetch Arbitrum balances for an address."""
    try:
        async with ArbitrumClient() as client:
            # Get ETH balance
            eth_balance = await client.get_balance(address)
            
            # For USDC on Arbitrum, we'd need to call the contract
            # For now, return 0 (can be enhanced with contract calls)
            usdc_balance = 0.0
            
            return ChainBalance(
                address=address,
                native_balance=float(eth_balance),
                native_symbol="ETH",
                tokens=[
                    TokenBalance(
                        token=USDC_CONTRACT_ARBITRUM,
                        symbol="USDC",
                        balance=usdc_balance,
                        decimals=6,
                        usd_value=usdc_balance
                    )
                ]
            )
    except Exception as e:
        logger.error(f"Failed to fetch Arbitrum balances: {e}")
        return None


def _check_sufficient_funds(
    solana: Optional[ChainBalance],
    arbitrum: Optional[ChainBalance]
) -> tuple[bool, str]:
    """
    Check if user has sufficient funds to trade.
    
    Returns:
        (has_sufficient, reason)
    """
    if not solana and not arbitrum:
        return False, "No wallet addresses configured"
    
    # Check Solana
    if solana:
        if solana.native_balance < 0.05:  # Need SOL for gas
            return False, f"Insufficient SOL for gas: {solana.native_balance:.4f} SOL (need 0.05)"
        
        usdc_solana = next((t for t in solana.tokens if t.symbol == "USDC"), None)
        if not usdc_solana or usdc_solana.balance < 10:
            balance = usdc_solana.balance if usdc_solana else 0
            return False, f"Insufficient USDC on Solana: ${balance:.2f} (need $10)"
    else:
        return False, "Solana wallet not configured"
    
    # Check Arbitrum (warn if low, but don't block)
    if arbitrum:
        if arbitrum.native_balance < 0.001:  # Need ETH for gas
            logger.warning("Low ETH balance on Arbitrum for gas")
        
        usdc_arbitrum = next((t for t in arbitrum.tokens if t.symbol == "USDC"), None)
        if not usdc_arbitrum or usdc_arbitrum.balance < 10:
            balance = usdc_arbitrum.balance if usdc_arbitrum else 0
            return False, f"Insufficient USDC on Arbitrum: ${balance:.2f} (need $10)"
    else:
        return False, "Arbitrum wallet not configured"
    
    return True, ""


@router.get("", response_model=BalancesResponse)
async def get_balances(
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db)
) -> BalancesResponse:
    """
    Get wallet balances for the current user.
    
    Returns balances for both Solana and Arbitrum wallets.
    Requires authentication.
    """
    # Get user's wallet addresses from database
    row = await db.fetchone(
        "SELECT solana_address, evm_address FROM users WHERE id = ?",
        (user.user_id,)
    )
    
    if not row:
        raise HTTPException(404, "User not found")
    
    solana_address = row.get("solana_address")
    evm_address = row.get("evm_address")
    
    # Fetch balances
    solana_balance = None
    arbitrum_balance = None
    
    if solana_address:
        solana_balance = await _get_solana_balances(solana_address)
    
    if evm_address:
        arbitrum_balance = await _get_arbitrum_balances(evm_address)
    
    # Check if sufficient funds
    has_sufficient, reason = _check_sufficient_funds(solana_balance, arbitrum_balance)
    
    if not has_sufficient:
        logger.info(f"User {user.user_id} has insufficient funds: {reason}")
    
    # Calculate total USD value
    total_usd = 0.0
    if solana_balance:
        for token in solana_balance.tokens:
            if token.usd_value:
                total_usd += token.usd_value
    if arbitrum_balance:
        for token in arbitrum_balance.tokens:
            if token.usd_value:
                total_usd += token.usd_value
    
    return BalancesResponse(
        solana=solana_balance,
        arbitrum=arbitrum_balance,
        total_usd_value=total_usd if total_usd > 0 else None,
        has_sufficient_funds=has_sufficient
    )


@router.get("/check")
async def check_funds(
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db)
) -> dict:
    """
    Quick check if user has sufficient funds to trade.
    
    Returns simplified response for trading eligibility check.
    """
    balances = await get_balances(user, db)
    
    return {
        "can_trade": balances.has_sufficient_funds,
        "solana_address": balances.solana.address if balances.solana else None,
        "arbitrum_address": balances.arbitrum.address if balances.arbitrum else None,
        "sol_balance": balances.solana.native_balance if balances.solana else 0,
        "eth_balance": balances.arbitrum.native_balance if balances.arbitrum else 0,
    }
