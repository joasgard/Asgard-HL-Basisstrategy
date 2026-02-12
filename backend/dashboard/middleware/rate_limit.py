"""
Redis-backed rate limiting middleware.

Uses sliding window counter with Redis INCR + EXPIRE.
Default limits:
  - Authenticated users: 60 requests/minute
  - Unauthenticated IPs: 20 requests/minute
"""

import time
import logging
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Rate limit defaults
AUTHENTICATED_LIMIT = 60    # requests per window
UNAUTHENTICATED_LIMIT = 20  # requests per window
WINDOW_SECONDS = 60         # sliding window size

RATE_LIMIT_PREFIX = "ratelimit:"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-backed sliding window rate limiter.

    Applied to all /api/v1 routes. Uses user_id for authenticated
    requests, client IP for unauthenticated.
    """

    def __init__(
        self,
        app,
        authenticated_limit: int = AUTHENTICATED_LIMIT,
        unauthenticated_limit: int = UNAUTHENTICATED_LIMIT,
        window_seconds: int = WINDOW_SECONDS,
    ):
        super().__init__(app)
        self.authenticated_limit = authenticated_limit
        self.unauthenticated_limit = unauthenticated_limit
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next) -> Response:
        # Only rate limit API routes
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)

        # Skip health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        # Determine identity and limit
        session_id = request.cookies.get("session_id")
        client_ip = request.client.host if request.client else "unknown"

        if session_id:
            # Authenticated: rate limit by session
            key = f"{RATE_LIMIT_PREFIX}user:{session_id}"
            limit = self.authenticated_limit
        else:
            # Unauthenticated: rate limit by IP
            key = f"{RATE_LIMIT_PREFIX}ip:{client_ip}"
            limit = self.unauthenticated_limit

        # Check rate limit
        allowed, remaining, retry_after = await self._check_limit(key, limit)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response

    async def _check_limit(self, key: str, limit: int) -> tuple:
        """
        Check and increment rate limit counter.

        Returns:
            (allowed: bool, remaining: int, retry_after: int)
        """
        try:
            from shared.redis_client import get_redis
            redis = await get_redis()

            # Increment counter
            current = await redis.incr(key)

            if current == 1:
                # First request in window — set expiry
                await redis.expire(key, self.window_seconds)

            if current > limit:
                # Over limit — get TTL for Retry-After
                ttl = await redis.ttl(key)
                return False, 0, max(ttl, 1)

            remaining = limit - current
            return True, remaining, 0

        except Exception as e:
            # If Redis is down, allow the request (fail open)
            logger.warning(f"Rate limit check failed: {e}")
            return True, limit, 0
