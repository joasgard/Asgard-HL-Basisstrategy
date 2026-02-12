"""
API endpoint to check wallet status for users.

Wallet creation is handled by Privy's frontend SDK (createOnLogin: 'all-users').
This endpoint reads wallet addresses from Privy's user profile.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.dashboard.auth import get_current_user
from backend.dashboard.privy_client import get_privy_client
from shared.common.schemas import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wallet-setup", tags=["wallet-setup"])


class WalletSetupResponse(BaseModel):
    success: bool
    message: str
    solana_address: Optional[str] = None
    ethereum_address: Optional[str] = None


@router.post("/ensure-wallets", response_model=WalletSetupResponse)
async def ensure_wallets(
    user: User = Depends(get_current_user),
):
    """
    Check that user has both Ethereum and Solana wallets.
    Wallets are created by the frontend Privy SDK — this just reads them.
    """
    privy = get_privy_client()

    try:
        result = await privy.get_user_wallet_addresses(user.user_id)
        solana_address = result.get("solana_address")
        ethereum_address = result.get("ethereum_address")

        if not solana_address and not ethereum_address:
            return WalletSetupResponse(
                success=False,
                message="No wallets found. Please reconnect to create wallets.",
            )

        return WalletSetupResponse(
            success=True,
            message="Wallets found",
            solana_address=solana_address,
            ethereum_address=ethereum_address,
        )

    except Exception as e:
        logger.error(f"Error checking wallets: {e}")
        raise HTTPException(500, f"Failed to check wallets: {str(e)}")


@router.get("/wallet-status")
async def wallet_status(
    user: User = Depends(get_current_user),
):
    """Get current wallet status for the user."""
    privy = get_privy_client()

    try:
        result = await privy.get_user_wallet_addresses(user.user_id)

        solana_address = result.get("solana_address")
        ethereum_address = result.get("ethereum_address")

        wallets = []
        if ethereum_address:
            wallets.append({"chain_type": "ethereum", "address": ethereum_address})
        if solana_address:
            wallets.append({"chain_type": "solana", "address": solana_address})

        return {
            "user_id": user.user_id,
            "wallets": wallets,
            "has_ethereum": ethereum_address is not None,
            "has_solana": solana_address is not None,
        }

    except Exception as e:
        logger.error(f"Error getting wallet status: {e}")
        raise HTTPException(500, f"Failed to get wallet status: {str(e)}")
