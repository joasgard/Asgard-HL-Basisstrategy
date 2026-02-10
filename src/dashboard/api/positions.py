"""Positions API endpoints."""

import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import uuid
import json
import logging

from src.dashboard.auth import require_viewer, require_operator
from src.dashboard.dependencies import require_bot_bridge
from src.dashboard.events_manager import (
    publish_position_opened, publish_position_closed
)
from src.shared.schemas import User, PositionSummary, PositionDetail
from src.db.database import get_db, Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/positions", tags=["positions"])


class OpenPositionRequest(BaseModel):
    """Request to open a new position."""
    asset: str = Field(..., description="Asset symbol (SOL, jitoSOL, jupSOL, INF)")
    leverage: float = Field(3.0, ge=1.1, le=4.0, description="Leverage multiplier (1.1x - 4x)")
    size_usd: float = Field(..., ge=100, description="Total position size in USD (both legs combined). Min $100.")
    venue: Optional[str] = Field(None, description="Preferred venue (kamino, drift, marginfi, solend)")


class OpenPositionResponse(BaseModel):
    """Response from opening a position."""
    success: bool
    message: str
    job_id: Optional[str] = None
    position_id: Optional[str] = None


class JobStatusResponse(BaseModel):
    """Status of a position opening job."""
    job_id: str
    status: str  # pending, running, completed, failed, cancelled
    position_id: Optional[str] = None
    error: Optional[str] = None
    error_stage: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    params: Optional[dict] = None


@router.get("", response_model=List[PositionSummary])
async def list_positions(user: User = Depends(require_viewer)):
    """
    List all open positions for the authenticated user.
    Requires viewer role or higher.
    """
    bot_bridge = require_bot_bridge()
    
    try:
        positions = await bot_bridge.get_positions(user_id=user.user_id)
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
        # First check if position belongs to user
        positions = await bot_bridge.get_positions(user_id=user.user_id)
        if position_id not in positions:
            raise HTTPException(404, "Position not found")
        
        detail = await bot_bridge.get_position_detail(position_id)
        return detail
    except HTTPException:
        raise
    except Exception as e:
        if "404" in str(e):
            raise HTTPException(404, "Position not found")
        raise HTTPException(503, f"Bot unavailable: {e}")


@router.post("/open", response_model=OpenPositionResponse)
async def open_position(
    request: OpenPositionRequest,
    user: User = Depends(require_operator),
    db: Database = Depends(get_db)
):
    """
    Open a new delta-neutral position.
    
    This creates an async job that will:
    1. Fetch current market rates
    2. Run preflight checks
    3. Open Asgard long position
    4. Open Hyperliquid short position
    5. Return position details
    
    Returns a job_id that can be polled via /jobs/{job_id}
    """
    job_id = str(uuid.uuid4())
    
    try:
        # Create job record
        await db.execute(
            """
            INSERT INTO position_jobs 
            (job_id, user_id, status, params, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (job_id, user.user_id, "pending", request.model_dump_json())
        )
        await db._connection.commit()
        
        # Trigger background execution
        asyncio.create_task(_execute_position_job(job_id, request, user.user_id, db))
        
        logger.info(f"Created position job {job_id} for user {user.user_id}")
        
        return OpenPositionResponse(
            success=True,
            message="Position opening initiated. Poll /positions/jobs/{job_id} for status.",
            job_id=job_id
        )
        
    except Exception as e:
        logger.error(f"Failed to create position job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _execute_position_job(
    job_id: str,
    request: OpenPositionRequest,
    user_id: str,
    db: Database
):
    """
    Execute position opening job in background.
    """
    from src.dashboard.dependencies import get_bot_bridge
    
    try:
        # Update status to running
        await db.execute(
            "UPDATE position_jobs SET status = ?, started_at = datetime('now') WHERE job_id = ?",
            ("running", job_id)
        )
        await db._connection.commit()
        
        # Get bot bridge
        bot_bridge = get_bot_bridge()
        if not bot_bridge:
            raise Exception("Bot bridge not available")
        
        # Call bot to open position
        result = await bot_bridge.open_position(
            asset=request.asset,
            leverage=request.leverage,
            size_usd=request.size_usd,
            protocol=request.venue,
            user_id=user_id
        )
        
        # Update job record with result
        if result.get("success"):
            await db.execute(
                """
                UPDATE position_jobs 
                SET status = ?, position_id = ?, result = ?, completed_at = datetime('now')
                WHERE job_id = ?
                """,
                ("completed", result.get("position_id"), json.dumps(result), job_id)
            )
            await db._connection.commit()
            
            # Publish event for real-time updates
            await publish_position_opened({
                "position_id": result.get("position_id"),
                "asset": request.asset,
                "leverage": request.leverage,
                "size_usd": request.size_usd,
                "protocol": result.get("selected_protocol"),
                "user_id": user_id
            })
            
            logger.info(f"Position job {job_id} completed successfully")
        else:
            # Failed - store error details
            error_stage = result.get("stage", "unknown")
            error_msg = result.get("error", "Unknown error")
            
            await db.execute(
                """
                UPDATE position_jobs 
                SET status = ?, error = ?, error_stage = ?, result = ?, completed_at = datetime('now')
                WHERE job_id = ?
                """,
                ("failed", error_msg, error_stage, json.dumps(result), job_id)
            )
            logger.error(f"Position job {job_id} failed at stage {error_stage}: {error_msg}")
        
        await db._connection.commit()
        
    except Exception as e:
        logger.error(f"Position job {job_id} crashed: {e}", exc_info=True)
        try:
            await db.execute(
                "UPDATE position_jobs SET status = ?, error = ?, completed_at = datetime('now') WHERE job_id = ?",
                ("failed", str(e), job_id)
            )
            await db._connection.commit()
        except Exception:
            pass  # Best effort


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    user: User = Depends(require_viewer),
    db: Database = Depends(get_db)
):
    """Get status of a position opening job."""
    row = await db.fetchone(
        """
        SELECT job_id, status, position_id, error, error_stage, 
               created_at, completed_at, params
        FROM position_jobs WHERE job_id = ?
        """,
        (job_id,)
    )
    
    if not row:
        raise HTTPException(404, "Job not found")
    
    # Parse params JSON
    params = None
    if row["params"]:
        try:
            params = json.loads(row["params"])
        except json.JSONDecodeError:
            pass
    
    return JobStatusResponse(
        job_id=row["job_id"],
        status=row["status"],
        position_id=row["position_id"],
        error=row["error"],
        error_stage=row["error_stage"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        params=params
    )


class ClosePositionResponse(BaseModel):
    """Response from closing a position."""
    success: bool
    message: str
    position_id: str
    job_id: Optional[str] = None


@router.post("/{position_id}/close", response_model=ClosePositionResponse)
async def close_position(
    position_id: str,
    user: User = Depends(require_operator),
    db: Database = Depends(get_db)
):
    """
    Close a delta-neutral position.
    
    This creates an async job that will:
    1. Close Hyperliquid short position
    2. Close Asgard long position
    3. Return completion status
    
    Returns a job_id that can be polled via /jobs/{job_id}
    """
    job_id = str(uuid.uuid4())
    
    try:
        # Verify position belongs to user
        bot_bridge = require_bot_bridge()
        user_positions = await bot_bridge.get_positions(user_id=user.user_id)
        if position_id not in user_positions:
            raise HTTPException(404, "Position not found or does not belong to user")
        
        # Create job record
        await db.execute(
            """
            INSERT INTO position_jobs 
            (job_id, user_id, status, params, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (job_id, user.user_id, "pending", json.dumps({
                "action": "close",
                "position_id": position_id
            }))
        )
        await db._connection.commit()
        
        # Trigger background execution
        asyncio.create_task(_execute_close_job(job_id, position_id, user.user_id, db))
        
        logger.info(f"Created close job {job_id} for position {position_id}, user {user.user_id}")
        
        return ClosePositionResponse(
            success=True,
            message="Position closing initiated. Poll /positions/jobs/{job_id} for status.",
            position_id=position_id,
            job_id=job_id
        )
        
    except Exception as e:
        logger.error(f"Failed to create close job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _execute_close_job(
    job_id: str,
    position_id: str,
    user_id: str,
    db: Database
):
    """
    Execute position closing job in background.
    """
    from src.dashboard.dependencies import get_bot_bridge
    
    try:
        # Update status to running
        await db.execute(
            "UPDATE position_jobs SET status = ?, started_at = datetime('now') WHERE job_id = ?",
            ("running", job_id)
        )
        await db._connection.commit()
        
        # Get bot bridge
        bot_bridge = get_bot_bridge()
        if not bot_bridge:
            raise Exception("Bot bridge not available")
        
        # Call bot to close position
        result = await bot_bridge.close_position(
            position_id=position_id,
            reason="manual"
        )
        
        # Update job record with result
        if result.get("success"):
            await db.execute(
                """
                UPDATE position_jobs 
                SET status = ?, result = ?, completed_at = datetime('now')
                WHERE job_id = ?
                """,
                ("completed", json.dumps(result), job_id)
            )
            await db._connection.commit()
            
            # Publish event for real-time updates
            await publish_position_closed(
                position_id=position_id,
                pnl_data={
                    "total_pnl": result.get("total_pnl", 0),
                    "user_id": user_id
                }
            )
            
            logger.info(f"Close job {job_id} completed successfully")
        else:
            error_msg = result.get("error", "Unknown error")
            await db.execute(
                """
                UPDATE position_jobs 
                SET status = ?, error = ?, result = ?, completed_at = datetime('now')
                WHERE job_id = ?
                """,
                ("failed", error_msg, json.dumps(result), job_id)
            )
            logger.error(f"Close job {job_id} failed: {error_msg}")
        
        await db._connection.commit()
        
    except Exception as e:
        logger.error(f"Close job {job_id} crashed: {e}", exc_info=True)
        try:
            await db.execute(
                "UPDATE position_jobs SET status = ?, error = ?, completed_at = datetime('now') WHERE job_id = ?",
                ("failed", str(e), job_id)
            )
            await db._connection.commit()
        except Exception:
            pass  # Best effort


@router.get("/jobs", response_model=List[JobStatusResponse])
async def list_jobs(
    user: User = Depends(require_viewer),
    db: Database = Depends(get_db),
    limit: int = 10
):
    """List recent position opening jobs for the user."""
    rows = await db.fetchall(
        """
        SELECT job_id, status, position_id, error, error_stage,
               created_at, completed_at, params
        FROM position_jobs 
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user.user_id, limit)
    )
    
    results = []
    for row in rows:
        params = None
        if row["params"]:
            try:
                params = json.loads(row["params"])
                # Add action type for close jobs
                if params.get("action") == "close":
                    params["action"] = "close"
            except json.JSONDecodeError:
                pass
        
        results.append(JobStatusResponse(
            job_id=row["job_id"],
            status=row["status"],
            position_id=row["position_id"],
            error=row["error"],
            error_stage=row["error_stage"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            params=params
        ))
    
    return results
