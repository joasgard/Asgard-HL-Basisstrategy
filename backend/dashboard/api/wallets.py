"""
Server wallet API endpoints.

Returns server wallet addresses and provisioning status for the
current user.  Used by the frontend to poll after login until wallets
are ready, and to show deposit addresses.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.dashboard.auth import get_current_user, User
from shared.db.database import get_db, Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wallets", tags=["wallets"])


class ServerWalletsResponse(BaseModel):
    """Server wallet status for a user."""
    ready: bool
    evm_wallet_id: Optional[str] = None
    evm_address: Optional[str] = None
    solana_wallet_id: Optional[str] = None
    solana_address: Optional[str] = None


@router.get("/server", response_model=ServerWalletsResponse)
async def get_server_wallets(
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> ServerWalletsResponse:
    """Return the current user's server wallet addresses.

    If wallets have not been provisioned yet, triggers provisioning
    and returns ``ready: false``.  The frontend should poll this
    endpoint until ``ready: true``.
    """
    row = await db.fetchone(
        """SELECT server_evm_wallet_id, server_evm_address,
                  server_solana_wallet_id, server_solana_address
           FROM users WHERE id = $1""",
        (user.user_id,),
    )

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    has_both = (
        row.get("server_evm_wallet_id") is not None
        and row.get("server_solana_wallet_id") is not None
    )

    if has_both:
        return ServerWalletsResponse(
            ready=True,
            evm_wallet_id=row["server_evm_wallet_id"],
            evm_address=row["server_evm_address"],
            solana_wallet_id=row["server_solana_wallet_id"],
            solana_address=row["server_solana_address"],
        )

    # Wallets not ready yet — trigger provisioning if not already running.
    import asyncio
    from bot.venues.server_wallets import ServerWalletService

    async def _provision():
        try:
            svc = ServerWalletService(db)
            wallets = await svc.ensure_wallets_for_user(user.user_id)
            logger.info(
                "server_wallets_provisioned_via_poll",
                extra={
                    "user_id": user.user_id,
                    "evm_wallet_id": wallets.evm_wallet_id,
                    "solana_wallet_id": wallets.solana_wallet_id,
                },
            )
        except Exception:
            logger.exception(
                "server_wallet_provisioning_failed_via_poll",
                extra={"user_id": user.user_id},
            )

    asyncio.create_task(_provision())

    return ServerWalletsResponse(
        ready=False,
        evm_address=row.get("server_evm_address"),
        solana_address=row.get("server_solana_address"),
    )
