"""
Server-Sent Events (SSE) API endpoints for real-time updates.

Provides live streaming of:
- Position updates (opened, closed, PnL changes)
- Funding rate updates
- Bot status changes
- Balance updates
"""

import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.dashboard.auth import get_current_user, User
from backend.dashboard.events_manager import event_manager, Event

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def event_stream(
    request: Request,
    user: User = Depends(get_current_user)
):
    """
    SSE endpoint for real-time events.
    
    Connects to the event stream and receives live updates:
    - position_opened: New position created
    - position_closed: Position closed with PnL
    - position_update: PnL or health factor changes
    - rate_update: Funding rates updated
    - bot_status: Bot paused/resumed/connected
    - balance_update: Wallet balance changes
    - ping: Keepalive every 30 seconds
    
    Example JavaScript usage:
        const eventSource = new EventSource('/api/v1/events/stream');
        eventSource.onmessage = (e) => {
            const event = JSON.parse(e.data);
            console.log(event.type, event.data);
        };
    
    Returns:
        text/event-stream with JSON-encoded events
    """
    # Ensure event manager is running
    await event_manager.start()
    
    # Subscribe to events
    queue = await event_manager.subscribe()
    
    async def generate() -> AsyncGenerator[str, None]:
        """Generate SSE stream."""
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                # Get event from queue (with timeout for periodic checks)
                try:
                    event: Event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    # No event, check connection and continue
                    continue
                
        except asyncio.CancelledError:
            # Client disconnected
            pass
        finally:
            # Unsubscribe when done
            await event_manager.unsubscribe(queue)
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.get("/status")
async def get_event_status(user: User = Depends(get_current_user)):
    """
    Get event system status.
    
    Returns:
        Current subscriber count and system health
    """
    return {
        "status": "healthy",
        "subscribers": event_manager.get_subscriber_count(),
        "streaming": True
    }
