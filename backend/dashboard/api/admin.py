"""Admin API endpoints (7.4.3).

Protected by admin API key (not user session auth).
"""
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from shared.db.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

KILL_SWITCH_FILE = Path("/data/emergency.stop")


def _verify_admin_key(x_admin_key: str = Header(...)) -> str:
    """Verify admin API key from header."""
    expected = os.environ.get("ADMIN_API_KEY", "")
    if not expected:
        # Try loading from secrets file
        try:
            expected = Path("secrets/admin_api_key.txt").read_text().strip()
        except FileNotFoundError:
            raise HTTPException(503, "Admin API key not configured")

    if not expected or x_admin_key != expected:
        raise HTTPException(403, "Invalid admin API key")
    return x_admin_key


class KillSwitchResponse(BaseModel):
    success: bool
    message: str
    active: bool


@router.get("/kill-switch", response_model=KillSwitchResponse)
async def get_kill_switch_status(admin_key: str = Header(None, alias="X-Admin-Key")):
    """Check if the global kill switch is active."""
    active = KILL_SWITCH_FILE.exists()
    return KillSwitchResponse(
        success=True,
        message="Kill switch is ACTIVE" if active else "Kill switch is inactive",
        active=active,
    )


@router.post("/kill-switch", response_model=KillSwitchResponse)
async def activate_kill_switch(
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Activate global kill switch — pauses ALL users immediately.

    Creates the emergency stop file and pauses all users in DB.
    """
    _verify_admin_key(x_admin_key)

    # Create kill switch file
    KILL_SWITCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    KILL_SWITCH_FILE.write_text(f"activated at {datetime.utcnow().isoformat()}\n")

    # Pause all users in DB
    db = await get_db()
    result = await db.execute(
        """UPDATE user_strategy_config
           SET enabled = FALSE, paused_at = NOW(), paused_reason = 'admin_kill_switch'
           WHERE enabled = TRUE OR paused_at IS NULL""",
    )

    logger.critical("KILL SWITCH ACTIVATED by admin")

    return KillSwitchResponse(
        success=True,
        message="Kill switch activated. All users paused.",
        active=True,
    )


@router.delete("/kill-switch", response_model=KillSwitchResponse)
async def deactivate_kill_switch(
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Deactivate global kill switch.

    Removes the emergency stop file. Users remain paused until they
    individually resume — this only lifts the global block.
    """
    _verify_admin_key(x_admin_key)

    if KILL_SWITCH_FILE.exists():
        KILL_SWITCH_FILE.unlink()

    logger.warning("KILL SWITCH DEACTIVATED by admin")

    return KillSwitchResponse(
        success=True,
        message="Kill switch deactivated. Users must individually resume.",
        active=False,
    )
