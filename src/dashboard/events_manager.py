"""
Event manager for real-time updates via Server-Sent Events (SSE).

Provides publish/subscribe pattern for broadcasting events to connected clients.
Used for real-time position updates, rate changes, and bot status notifications.
"""

import asyncio
import json
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from src.utils.logger import get_logger

logger = get_logger(__name__)


class EventType(Enum):
    """Types of events that can be broadcast."""
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    POSITION_UPDATE = "position_update"
    RATE_UPDATE = "rate_update"
    BOT_STATUS = "bot_status"
    BALANCE_UPDATE = "balance_update"
    ERROR = "error"
    PING = "ping"


@dataclass
class Event:
    """Event data structure."""
    type: EventType
    data: Dict[str, Any]
    timestamp: str
    
    def to_sse(self) -> str:
        """Convert to SSE format."""
        payload = json.dumps({
            'type': self.type.value,
            'data': self.data,
            'timestamp': self.timestamp
        })
        return f"data: {payload}\n\n"


class EventManager:
    """
    Manages event subscriptions and broadcasting.
    
    Singleton pattern - one event manager per process.
    
    Usage:
        # Subscribe to events
        async for event in event_manager.subscribe():
            yield event.to_sse()
        
        # Publish event
        await event_manager.publish(EventType.POSITION_OPENED, {...})
    """
    
    _instance: Optional['EventManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._subscribers: Dict[str, asyncio.Queue] = {}
        self._subscriber_counter = 0
        self._lock = asyncio.Lock()
        self._initialized = True
        
        # Start ping task
        self._ping_task: Optional[asyncio.Task] = None
        
        logger.info("EventManager initialized")
    
    async def start(self):
        """Start background tasks."""
        if self._ping_task is None or self._ping_task.done():
            self._ping_task = asyncio.create_task(self._ping_loop())
            logger.info("EventManager started")
    
    async def stop(self):
        """Stop background tasks."""
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        
        # Clear all subscribers
        async with self._lock:
            self._subscribers.clear()
        
        logger.info("EventManager stopped")
    
    async def _ping_loop(self):
        """Send ping events every 30 seconds to keep connections alive."""
        while True:
            try:
                await asyncio.sleep(30)
                await self.publish(EventType.PING, {"message": "keepalive"})
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ping error: {e}")
    
    async def subscribe(self) -> asyncio.Queue:
        """
        Subscribe to events.
        
        Returns:
            Queue that receives Event objects
        """
        async with self._lock:
            self._subscriber_counter += 1
            subscriber_id = f"sub_{self._subscriber_counter}"
            queue = asyncio.Queue(maxsize=100)  # Backpressure
            self._subscribers[subscriber_id] = queue
            
        logger.debug(f"New subscriber: {subscriber_id} (total: {len(self._subscribers)})")
        
        # Send initial connection event
        await queue.put(Event(
            type=EventType.BOT_STATUS,
            data={"status": "connected", "message": "Event stream connected"},
            timestamp=datetime.utcnow().isoformat()
        ))
        
        return queue
    
    async def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe a queue."""
        async with self._lock:
            to_remove = None
            for sub_id, sub_queue in self._subscribers.items():
                if sub_queue is queue:
                    to_remove = sub_id
                    break
            
            if to_remove:
                del self._subscribers[to_remove]
                logger.debug(f"Subscriber removed: {to_remove} (total: {len(self._subscribers)})")
    
    async def publish(self, event_type: EventType, data: Dict[str, Any]):
        """
        Publish an event to all subscribers.
        
        Args:
            event_type: Type of event
            data: Event payload
        """
        event = Event(
            type=event_type,
            data=data,
            timestamp=datetime.utcnow().isoformat()
        )
        
        async with self._lock:
            dead_subscribers = []
            
            for sub_id, queue in self._subscribers.items():
                try:
                    # Non-blocking put with timeout
                    await asyncio.wait_for(queue.put(event), timeout=0.1)
                except asyncio.TimeoutError:
                    # Queue full, subscriber is slow
                    logger.warning(f"Subscriber {sub_id} queue full, dropping event")
                except Exception as e:
                    logger.error(f"Failed to send to subscriber {sub_id}: {e}")
                    dead_subscribers.append(sub_id)
            
            # Clean up dead subscribers
            for sub_id in dead_subscribers:
                del self._subscribers[sub_id]
                logger.info(f"Removed dead subscriber: {sub_id}")
        
        # Log important events
        if event_type != EventType.PING:
            logger.debug(f"Published {event_type.value} to {len(self._subscribers)} subscribers")
    
    def get_subscriber_count(self) -> int:
        """Get number of active subscribers."""
        return len(self._subscribers)


# Global event manager instance
event_manager = EventManager()


# Helper functions for common events

async def publish_position_opened(position_data: Dict[str, Any]):
    """Publish position opened event."""
    await event_manager.publish(EventType.POSITION_OPENED, position_data)


async def publish_position_closed(position_id: str, pnl_data: Dict[str, Any]):
    """Publish position closed event."""
    await event_manager.publish(EventType.POSITION_CLOSED, {
        "position_id": position_id,
        **pnl_data
    })


async def publish_position_update(position_id: str, update_data: Dict[str, Any]):
    """Publish position update (PnL, health, etc)."""
    await event_manager.publish(EventType.POSITION_UPDATE, {
        "position_id": position_id,
        **update_data
    })


async def publish_rate_update(rates_data: Dict[str, Any]):
    """Publish funding rate update."""
    await event_manager.publish(EventType.RATE_UPDATE, rates_data)


async def publish_bot_status(status: str, message: str = None):
    """Publish bot status change."""
    await event_manager.publish(EventType.BOT_STATUS, {
        "status": status,
        "message": message
    })


async def publish_balance_update(balance_data: Dict[str, Any]):
    """Publish wallet balance update."""
    await event_manager.publish(EventType.BALANCE_UPDATE, balance_data)


async def publish_error(error_message: str, context: Dict[str, Any] = None):
    """Publish error event."""
    await event_manager.publish(EventType.ERROR, {
        "message": error_message,
        "context": context or {}
    })
