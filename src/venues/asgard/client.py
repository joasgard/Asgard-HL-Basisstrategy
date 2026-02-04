"""
Asgard Finance API Client.

This module provides the base HTTP client for interacting with the Asgard Finance
margin trading API on Solana.

API Documentation:
- Base URL: https://v2-ultra-edge.asgard.finance/margin-trading
- Auth: X-API-Key header
- Rate Limiting: 1 req/sec public, configurable with API key
"""
import asyncio
from typing import Any, Optional
from urllib.parse import urljoin

import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AsgardAPIError(Exception):
    """Base exception for Asgard API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class AsgardAuthError(AsgardAPIError):
    """Raised when authentication fails (401)."""
    pass


class AsgardRateLimitError(AsgardAPIError):
    """Raised when rate limit is exceeded (429)."""
    pass


class AsgardClientError(AsgardAPIError):
    """Raised for 4xx client errors (excluding 401, 429)."""
    pass


class AsgardServerError(AsgardAPIError):
    """Raised for 5xx server errors."""
    pass


class AsgardClient:
    """
    Async HTTP client for Asgard Finance API.
    
    Features:
    - Automatic authentication via X-API-Key header
    - Rate limiting enforcement (1 req/sec default)
    - Exponential backoff retry for server errors
    - Structured error handling
    
    Usage:
        async with AsgardClient() as client:
            markets = await client.get_markets()
    """
    
    BASE_URL = "https://v2-ultra-edge.asgard.finance/margin-trading"
    DEFAULT_RATE_LIMIT = 1.0  # 1 request per second for public endpoints
    MAX_RETRIES = 3
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        rate_limit_rps: Optional[float] = None,
    ):
        """
        Initialize Asgard client.
        
        Args:
            api_key: Asgard API key. If not provided, loads from settings.
            base_url: Override base URL for API.
            rate_limit_rps: Requests per second limit. Default 1.0 for public.
        """
        settings = get_settings()
        
        self.api_key = api_key or settings.asgard_api_key
        self.base_url = base_url or self.BASE_URL
        self.rate_limit_rps = rate_limit_rps or self.DEFAULT_RATE_LIMIT
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_request_time: Optional[float] = None
        self._lock = asyncio.Lock()
        
        if not self.api_key:
            logger.warning("Asgard API key not configured. Requests may fail.")
    
    async def __aenter__(self) -> "AsgardClient":
        """Async context manager entry."""
        await self._init_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    async def _init_session(self) -> None:
        """Initialize aiohttp session with default headers."""
        if self._session is None or self._session.closed:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            )
            logger.debug("Asgard client session initialized")
    
    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("Asgard client session closed")
    
    async def _enforce_rate_limit(self) -> None:
        """
        Enforce rate limiting between requests.
        
        Ensures at least (1/rate_limit_rps) seconds between requests.
        """
        async with self._lock:
            if self._last_request_time is not None:
                import time
                elapsed = time.time() - self._last_request_time
                min_interval = 1.0 / self.rate_limit_rps
                
                if elapsed < min_interval:
                    sleep_time = min_interval - elapsed
                    logger.debug(f"Rate limiting: sleeping {sleep_time:.3f}s")
                    await asyncio.sleep(sleep_time)
            
            import time
            self._last_request_time = time.time()
    
    def _handle_error(self, status: int, data: Any) -> None:
        """
        Handle HTTP error responses.
        
        Args:
            status: HTTP status code
            data: Response data (may contain error details)
            
        Raises:
            AsgardAuthError: For 401 responses
            AsgardRateLimitError: For 429 responses
            AsgardClientError: For other 4xx responses
            AsgardServerError: For 5xx responses
        """
        error_msg = "Unknown error"
        if isinstance(data, dict):
            error_msg = data.get("error", data.get("message", error_msg))
        
        if status == 401:
            raise AsgardAuthError(
                f"Authentication failed: {error_msg}",
                status_code=status,
                response_data=data,
            )
        elif status == 429:
            raise AsgardRateLimitError(
                f"Rate limit exceeded: {error_msg}",
                status_code=status,
                response_data=data,
            )
        elif 400 <= status < 500:
            raise AsgardClientError(
                f"Client error {status}: {error_msg}",
                status_code=status,
                response_data=data,
            )
        elif 500 <= status < 600:
            raise AsgardServerError(
                f"Server error {status}: {error_msg}",
                status_code=status,
                response_data=data,
            )
    
    @retry(
        retry=retry_if_exception_type((AsgardServerError, aiohttp.ClientError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict:
        """
        Make an HTTP request to the Asgard API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (without base URL)
            **kwargs: Additional arguments for aiohttp request
            
        Returns:
            Parsed JSON response
            
        Raises:
            AsgardAPIError: For API errors
            aiohttp.ClientError: For network errors
        """
        await self._init_session()
        await self._enforce_rate_limit()
        
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        
        logger.debug(f"Asgard API request: {method} {endpoint}")
        
        try:
            async with self._session.request(method, url, **kwargs) as response:
                data = await response.json()
                
                if response.status >= 400:
                    self._handle_error(response.status, data)
                
                logger.debug(f"Asgard API response: {response.status}")
                return data
                
        except aiohttp.ClientResponseError as e:
            logger.error(f"Asgard API response error: {e.status} - {e.message}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Asgard API client error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Asgard API request: {e}")
            raise
    
    async def _get(self, endpoint: str, **kwargs: Any) -> dict:
        """Make a GET request."""
        return await self._request("GET", endpoint, **kwargs)
    
    async def _post(self, endpoint: str, **kwargs: Any) -> dict:
        """Make a POST request."""
        return await self._request("POST", endpoint, **kwargs)
    
    # ==================== Public Endpoints ====================
    
    async def get_markets(self) -> dict:
        """
        Fetch all available margin trading strategies/markets.
        
        Returns:
            List of market data including:
            - token pairs
            - lending/borrowing rates
            - max borrow capacities
            - protocol information
            
        Example response:
            {
                "markets": [
                    {
                        "strategy": "SOL-USDC",
                        "protocol": 0,
                        "tokenAMint": "So111...",
                        "tokenBMint": "EPjF...",
                        "lendingRate": 0.05,
                        "borrowingRate": 0.08,
                        "tokenBMaxBorrowCapacity": 1000000
                    }
                ]
            }
        """
        return await self._get("/markets")
    
    async def health_check(self) -> dict:
        """
        Check API health status.
        
        Returns:
            Health status information
        """
        return await self._get("/health")
