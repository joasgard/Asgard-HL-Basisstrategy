"""
Timed cache decorator for dashboard.
"""

import time
import functools
from typing import Optional, Callable, Any
import asyncio


class TimedCache:
    """Simple timed cache with TTL."""
    
    def __init__(self, ttl_seconds: float = 5.0):
        self.ttl = ttl_seconds
        self._cache: dict = {}
        self._timestamps: dict = {}
        self._lock: Optional[asyncio.Lock] = None
    
    def _get_lock(self) -> asyncio.Lock:
        """Lazy initialization of lock for tests."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock
    
    def _is_fresh(self, key: str) -> bool:
        """Check if cache entry is still fresh."""
        if key not in self._timestamps:
            return False
        return time.time() - self._timestamps[key] < self.ttl
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached value if fresh."""
        async with self._get_lock():
            if self._is_fresh(key):
                return self._cache.get(key)
            return None
    
    async def set(self, key: str, value: Any):
        """Set cache value."""
        async with self._get_lock():
            self._cache[key] = value
            self._timestamps[key] = time.time()
    
    async def get_or_set(self, key: str, factory: Callable, *args, **kwargs) -> Any:
        """Get from cache or set using factory."""
        cached = await self.get(key)
        if cached is not None:
            return cached
        
        value = await factory(*args, **kwargs)
        await self.set(key, value)
        return value
    
    def invalidate(self, key: Optional[str] = None):
        """Invalidate cache entry or all entries."""
        if key:
            self._timestamps.pop(key, None)
        else:
            self._timestamps.clear()


def cached(ttl_seconds: float = 5.0):
    """
    Decorator to cache async function results.
    
    Usage:
        @cached(ttl_seconds=10)
        async def get_expensive_data():
            return await fetch_from_api()
    """
    cache = TimedCache(ttl_seconds)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            key_parts = [func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)
            
            # Try to get from cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Call function and cache result
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result)
            return result
        
        # Attach cache for external invalidation
        wrapper.cache = cache
        return wrapper
    
    return decorator
