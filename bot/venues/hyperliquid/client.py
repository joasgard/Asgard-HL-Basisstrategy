"""
Hyperliquid API Client.

This module provides the base HTTP client for interacting with the Hyperliquid
exchange API on Arbitrum.

API Documentation:
- Info: POST https://api.hyperliquid.xyz/info
- Exchange: POST https://api.hyperliquid.xyz/exchange
- All exchange actions require EIP-712 signatures
"""
import json
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class HyperliquidAPIError(Exception):
    """Base exception for Hyperliquid API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class HyperliquidAuthError(HyperliquidAPIError):
    """Raised when authentication/signature verification fails."""
    pass


class HyperliquidRateLimitError(HyperliquidAPIError):
    """Raised when rate limit is exceeded."""
    pass


class HyperliquidClientError(HyperliquidAPIError):
    """Raised for 4xx client errors."""
    pass


class HyperliquidServerError(HyperliquidAPIError):
    """Raised for 5xx server errors."""
    pass


class HyperliquidClient:
    """
    Async HTTP client for Hyperliquid API.
    
    Hyperliquid has two main endpoints:
    - /info: Read-only market data, no authentication required
    - /exchange: Trading operations, requires EIP-712 signed payloads
    
    Features:
    - Separate methods for info and exchange endpoints
    - Exponential backoff retry for server errors
    - Structured error handling
    
    Usage:
        async with HyperliquidClient() as client:
            # Read-only info call
            funding = await client.info({"type": "fundingRates"})
            
            # Exchange call (requires signature)
            result = await client.exchange(signed_payload)
    """
    
    API_BASE = "https://api.hyperliquid.xyz"
    MAX_RETRIES = 3
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize Hyperliquid client.
        
        Args:
            base_url: Override base URL for API.
        """
        self.base_url = base_url or self.API_BASE
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self) -> "HyperliquidClient":
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
            
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            )
            logger.debug("Hyperliquid client session initialized")
    
    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("Hyperliquid client session closed")
    
    def _handle_error(self, status: int, data: Any) -> None:
        """
        Handle HTTP error responses.
        
        Args:
            status: HTTP status code
            data: Response data (may contain error details)
            
        Raises:
            HyperliquidAuthError: For auth failures
            HyperliquidRateLimitError: For 429 responses
            HyperliquidClientError: For other 4xx responses
            HyperliquidServerError: For 5xx responses
        """
        error_msg = "Unknown error"
        if isinstance(data, dict):
            error_msg = data.get("error", data.get("message", error_msg))
        elif isinstance(data, str):
            error_msg = data
        
        if status == 401 or "signature" in error_msg.lower():
            raise HyperliquidAuthError(
                f"Authentication failed: {error_msg}",
                status_code=status,
                response_data=data,
            )
        elif status == 429:
            raise HyperliquidRateLimitError(
                f"Rate limit exceeded: {error_msg}",
                status_code=status,
                response_data=data,
            )
        elif 400 <= status < 500:
            raise HyperliquidClientError(
                f"Client error {status}: {error_msg}",
                status_code=status,
                response_data=data,
            )
        elif 500 <= status < 600:
            raise HyperliquidServerError(
                f"Server error {status}: {error_msg}",
                status_code=status,
                response_data=data,
            )
    
    @retry(
        retry=retry_if_exception_type((HyperliquidServerError, aiohttp.ClientError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _request(
        self,
        endpoint: str,
        payload: dict,
    ) -> dict:
        """
        Make an HTTP POST request to the Hyperliquid API.
        
        Args:
            endpoint: API endpoint ("/info" or "/exchange")
            payload: Request payload (JSON-serializable dict)
            
        Returns:
            Parsed JSON response
            
        Raises:
            HyperliquidAPIError: For API errors
            aiohttp.ClientError: For network errors
        """
        await self._init_session()
        
        url = urljoin(self.base_url, endpoint)
        
        logger.debug(f"Hyperliquid API request: POST {endpoint}")
        
        try:
            async with self._session.post(url, json=payload) as response:
                # HL sometimes returns text/plain or empty bodies for errors;
                # read raw text first, then try to parse as JSON.
                raw_text = await response.text()
                try:
                    data = json.loads(raw_text) if raw_text.strip() else raw_text
                except (ValueError, json.JSONDecodeError):
                    data = raw_text

                if response.status >= 400:
                    self._handle_error(response.status, data)
                
                # Check for error in response body (Hyperliquid returns 200 with errors)
                if isinstance(data, dict) and data.get("status") == "err":
                    error_msg = data.get("response", "Unknown error")
                    raise HyperliquidClientError(f"API error: {error_msg}", response_data=data)
                
                logger.debug(f"Hyperliquid API response: {response.status}")
                return data
                
        except aiohttp.ClientResponseError as e:
            logger.error(f"Hyperliquid API response error: {e.status} - {e.message}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Hyperliquid API client error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Hyperliquid API request: {e}")
            raise
    
    async def info(self, payload: dict) -> dict:
        """
        Make a request to the /info endpoint (read-only).
        
        No authentication required. Used for:
        - Fetching market data
        - Getting funding rates
        - Querying account state
        
        Args:
            payload: Request payload with "type" field
            
        Returns:
            API response data
            
        Example:
            funding = await client.info({"type": "fundingRates"})
        """
        return await self._request("/info", payload)
    
    async def exchange(self, payload: dict) -> dict:
        """
        Make a request to the /exchange endpoint (trading).
        
        Requires EIP-712 signed payload. Used for:
        - Placing orders
        - Cancelling orders
        - Updating leverage
        
        Args:
            payload: Signed action payload
            
        Returns:
            API response data
            
        Example:
            result = await client.exchange(signed_order_payload)
        """
        return await self._request("/exchange", payload)
    
    # ==================== Info Endpoint Helpers ====================
    
    async def get_meta_and_asset_contexts(self) -> dict:
        """
        Get metadata and asset contexts (includes funding rates).
        
        Returns:
            Dict with "meta" (universe info) and "assetCtxs" (per-asset context)
        """
        return await self.info({"type": "metaAndAssetCtxs"})
    
    async def get_clearinghouse_state(self, user_address: str) -> dict:
        """
        Get clearinghouse state for a user (positions, margin, etc.).
        
        Args:
            user_address: User's wallet address (0x...)
            
        Returns:
            Account state including positions, margin, and balances
        """
        return await self.info({
            "type": "clearinghouseState",
            "user": user_address,
        })
    
    async def get_funding_history(
        self,
        coin: str,
        start_time: int,
        end_time: Optional[int] = None,
    ) -> list:
        """
        Get historical funding rates for a coin.
        
        Args:
            coin: Coin symbol (e.g., "SOL")
            start_time: Start timestamp (milliseconds)
            end_time: End timestamp (milliseconds, defaults to now)
            
        Returns:
            List of funding rate entries
        """
        payload = {
            "type": "fundingHistory",
            "coin": coin,
            "startTime": start_time,
        }
        if end_time:
            payload["endTime"] = end_time
        
        return await self.info(payload)
    
    async def get_l2_book(self, coin: str) -> dict:
        """
        Get L2 order book for a coin.
        
        Args:
            coin: Coin symbol (e.g., "SOL")
            
        Returns:
            Order book with bids and asks
        """
        return await self.info({
            "type": "l2Book",
            "coin": coin,
        })
    
    async def get_all_mids(self) -> dict:
        """
        Get mid prices for all coins.
        
        Returns:
            Dict mapping coin symbols to mid prices
        """
        return await self.info({"type": "allMids"})
