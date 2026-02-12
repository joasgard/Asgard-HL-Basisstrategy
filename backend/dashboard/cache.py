"""
Redis-backed cache for dashboard.

Replaces in-memory TimedCache with Redis GET/SET + TTL.
Same interface so callers don't change.
"""

import json
import functools
from typing import Optional, Callable, Any

CACHE_PREFIX = "cache:"


class TimedCache:
    """Redis-backed timed cache with TTL."""

    def __init__(self, ttl_seconds: float = 5.0):
        self.ttl = int(ttl_seconds) or 1

    async def _get_redis(self):
        from shared.redis_client import get_redis
        return await get_redis()

    def _key(self, key: str) -> str:
        return f"{CACHE_PREFIX}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Get cached value if fresh."""
        redis = await self._get_redis()
        raw = await redis.get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(self, key: str, value: Any) -> None:
        """Set cache value with TTL."""
        redis = await self._get_redis()
        await redis.set(self._key(key), json.dumps(value, default=str), ex=self.ttl)

    async def get_or_set(self, key: str, factory: Callable, *args, **kwargs) -> Any:
        """Get from cache or set using factory."""
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = await factory(*args, **kwargs)
        await self.set(key, value)
        return value

    async def invalidate(self, key: Optional[str] = None) -> None:
        """Invalidate cache entry or all entries with prefix."""
        redis = await self._get_redis()
        if key:
            await redis.delete(self._key(key))
        else:
            # Invalidate all cache keys (scan and delete)
            async for k in redis.scan_iter(match=f"{CACHE_PREFIX}*", count=100):
                await redis.delete(k)


def cached(ttl_seconds: float = 5.0):
    """
    Decorator to cache async function results in Redis.

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
