"""
Redis client utility for shared state across processes.

Provides connection pooling and helpers for sessions, cache, events, and locking.
"""

import os
from typing import Optional

import redis.asyncio as aioredis

# Default Redis URL
DEFAULT_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Singleton pool
_redis_pool: Optional[aioredis.Redis] = None


async def get_redis(redis_url: str = DEFAULT_REDIS_URL) -> aioredis.Redis:
    """
    Get Redis connection from pool (singleton).

    Returns an aioredis.Redis instance backed by a connection pool.
    Safe to call from any coroutine — the pool is created once.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            redis_url,
            decode_responses=True,
            max_connections=20,
        )
    return _redis_pool


_redis_bytes_pool: Optional[aioredis.Redis] = None


async def get_redis_bytes(redis_url: str = DEFAULT_REDIS_URL) -> aioredis.Redis:
    """
    Get Redis connection that returns raw bytes (for binary data like encrypted DEKs).
    Uses a singleton pool to avoid connection leaks.
    """
    global _redis_bytes_pool
    if _redis_bytes_pool is None:
        _redis_bytes_pool = aioredis.from_url(
            redis_url,
            decode_responses=False,
            max_connections=5,
        )
    return _redis_bytes_pool


async def close_redis() -> None:
    """Close the Redis connection pools."""
    global _redis_pool, _redis_bytes_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
    if _redis_bytes_pool is not None:
        await _redis_bytes_pool.aclose()
        _redis_bytes_pool = None
