"""
Bridge between Dashboard and DeltaNeutralBot.
Implements stale-data caching for availability over consistency.
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
import httpx

from src.shared.schemas import BotStats, PositionSummary, PositionDetail, PauseState

logger = logging.getLogger(__name__)


class BotUnavailableError(Exception):
    """Raised when bot is not available."""
    pass


class BotBridge:
    """
    HTTP client for bot internal API with caching.
    
    Implements 5-second stale-data cache:
    - Returns fresh data if available
    - Returns cached data if bot slow (< 2s timeout)
    - Raises exception if no cached data available
    """
    
    def __init__(self, bot_api_url: str = "http://bot:8000", internal_token: str = None):
        self._api_url = bot_api_url
        self._internal_token = internal_token
        self._client = httpx.AsyncClient(
            base_url=bot_api_url,
            timeout=httpx.Timeout(5.0, connect=2.0)
        )
        
        # Cache storage
        self._cache: Dict[str, Any] = {}
        self._cache_timestamp: Dict[str, float] = {}
        self._cache_ttl = 5.0  # 5 seconds
        self._lock = asyncio.Lock()
        self._background_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start background cache refresh."""
        self._background_task = asyncio.create_task(self._background_refresh())
        logger.info("BotBridge started with background refresh")
    
    async def stop(self):
        """Stop background tasks."""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()
    
    async def _background_refresh(self):
        """Keep cache warm even without requests."""
        while True:
            await asyncio.sleep(5.0)
            try:
                await self.get_positions()
                await self.get_pause_state()
            except BotUnavailableError:
                logger.warning("Background refresh: bot unavailable")
            except Exception as e:
                logger.error(f"Background refresh failed: {e}")
    
    def _is_cache_fresh(self, key: str) -> bool:
        """Check if cache entry is still fresh."""
        if key not in self._cache_timestamp:
            return False
        return time.time() - self._cache_timestamp[key] < self._cache_ttl
    
    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached value if fresh."""
        if self._is_cache_fresh(key):
            return self._cache.get(key)
        return None
    
    def _set_cached(self, key: str, value: Any):
        """Cache a value."""
        self._cache[key] = value
        self._cache_timestamp[key] = time.time()
    
    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make authenticated request to bot API."""
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._internal_token}"
        
        try:
            response = await self._client.request(
                method, path, headers=headers, **kwargs
            )
            response.raise_for_status()
            return response
        except httpx.ConnectError as e:
            raise BotUnavailableError(f"Cannot connect to bot: {e}")
        except httpx.TimeoutException as e:
            raise BotUnavailableError(f"Bot request timeout: {e}")
    
    async def get_positions(self) -> Dict[str, PositionSummary]:
        """
        Get positions with caching.
        Returns stale data on timeout rather than fail.
        """
        cache_key = "positions"
        
        # Fast path: return cached data if fresh
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("Returning cached positions")
            return cached
        
        # Slow path: fetch from bot with short timeout
        async def _fetch():
            async with self._lock:
                response = await self._request("GET", "/internal/positions")
                data = response.json()
                
                positions = {
                    pos_id: PositionSummary(**pos_data)
                    for pos_id, pos_data in data.items()
                }
                
                self._set_cached(cache_key, positions)
                return positions
        
        try:
            return await asyncio.wait_for(_fetch(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.warning("Bot positions request timeout, using stale cache")
            cached = self._cache.get(cache_key)  # Use stale cache
            if cached is not None:
                return cached
            raise BotUnavailableError("No cached positions available")
        except BotUnavailableError:
            # Try to use stale cache
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.warning("Bot unavailable, returning stale positions")
                return cached
            raise
    
    async def get_position_detail(self, position_id: str) -> PositionDetail:
        """Get detailed position information."""
        cache_key = f"position_detail_{position_id}"
        
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        response = await self._request("GET", f"/internal/positions/{position_id}")
        detail = PositionDetail(**response.json())
        self._set_cached(cache_key, detail)
        return detail
    
    async def get_stats(self) -> BotStats:
        """Get bot statistics."""
        cache_key = "stats"
        
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        response = await self._request("GET", "/internal/stats")
        stats = BotStats(**response.json())
        self._set_cached(cache_key, stats)
        return stats
    
    async def get_pause_state(self) -> PauseState:
        """Get current pause state."""
        cache_key = "pause_state"
        
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        response = await self._request("GET", "/internal/pause-state")
        state = PauseState(**response.json())
        self._set_cached(cache_key, state)
        return state
    
    async def pause(self, api_key: str, reason: str, scope: str) -> bool:
        """Pause bot operations."""
        response = await self._request(
            "POST",
            "/internal/control/pause",
            json={"api_key": api_key, "reason": reason, "scope": scope}
        )
        result = response.json()["success"]
        if result:
            self.invalidate_cache("pause_state")
        return result
    
    async def resume(self, api_key: str) -> bool:
        """Resume bot operations."""
        response = await self._request(
            "POST",
            "/internal/control/resume",
            json={"api_key": api_key}
        )
        result = response.json()["success"]
        if result:
            self.invalidate_cache("pause_state")
        return result
    
    async def open_position(self, asset: str, leverage: float, size_usd: float, protocol: str = None) -> dict:
        """
        Open a new delta-neutral position.
        
        Args:
            asset: Asset symbol (SOL, jitoSOL, jupSOL, INF)
            leverage: Leverage multiplier (2.0 - 4.0)
            size_usd: Position size in USD
            protocol: Optional protocol override (kamino, drift, marginfi, solend)
            
        Returns:
            dict with success status and position details
        """
        payload = {
            "asset": asset,
            "leverage": leverage,
            "size_usd": size_usd
        }
        if protocol:
            payload["protocol"] = protocol
        
        response = await self._request(
            "POST",
            "/internal/positions/open",
            json=payload
        )
        result = response.json()
        
        # Invalidate positions cache on success
        if result.get("success"):
            self.invalidate_cache("positions")
        
        return result
    
    async def health_check(self) -> bool:
        """Check if bot is healthy."""
        try:
            response = await self._client.get("/health", timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False
    
    def invalidate_cache(self, key: str = None):
        """Invalidate cache entries."""
        if key:
            self._cache_timestamp.pop(key, None)
        else:
            self._cache_timestamp.clear()
