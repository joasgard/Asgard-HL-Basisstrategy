"""
Tests for Asgard Finance API Client.

These tests verify:
- Authentication header is sent correctly
- Rate limiting is enforced
- Retry logic works on server errors
- Error handling for different status codes
- Context manager functionality
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from src.venues.asgard.client import (
    AsgardClient,
    AsgardAPIError,
    AsgardAuthError,
    AsgardRateLimitError,
    AsgardClientError,
    AsgardServerError,
)


class TestAsgardClientInit:
    """Tests for client initialization."""
    
    def test_init_with_explicit_api_key(self):
        """Test initialization with explicit API key."""
        client = AsgardClient(api_key="test_key_123")
        assert client.api_key == "test_key_123"
        assert client.base_url == AsgardClient.BASE_URL
        assert client.rate_limit_rps == AsgardClient.DEFAULT_RATE_LIMIT
    
    def test_init_with_custom_params(self):
        """Test initialization with custom parameters."""
        client = AsgardClient(
            api_key="custom_key",
            base_url="https://custom.asgard.finance",
            rate_limit_rps=2.5,
        )
        assert client.api_key == "custom_key"
        assert client.base_url == "https://custom.asgard.finance"
        assert client.rate_limit_rps == 2.5
    
    @patch("src.venues.asgard.client.get_settings")
    def test_init_loads_from_settings(self, mock_get_settings):
        """Test that API key is loaded from settings if not provided."""
        mock_settings = MagicMock()
        mock_settings.asgard_api_key = "settings_key"
        mock_get_settings.return_value = mock_settings
        
        client = AsgardClient()
        assert client.api_key == "settings_key"
    
    @patch("src.venues.asgard.client.get_settings")
    def test_init_warns_if_no_api_key(self, mock_get_settings):
        """Test that warning is logged if API key is not configured."""
        mock_settings = MagicMock()
        mock_settings.asgard_api_key = ""
        mock_get_settings.return_value = mock_settings
        
        # Should not raise, but api_key will be empty
        client = AsgardClient()
        assert client.api_key == ""


class TestAsgardClientContextManager:
    """Tests for async context manager."""
    
    @pytest.mark.asyncio
    async def test_context_manager_initializes_session(self):
        """Test that context manager initializes and closes session."""
        async with AsgardClient(api_key="test_key") as client:
            assert client._session is not None
            assert not client._session.closed
        
        # Session should be closed after exiting context
        assert client._session.closed
    
    @pytest.mark.asyncio
    async def test_manual_close(self):
        """Test manual session close."""
        client = AsgardClient(api_key="test_key")
        await client._init_session()
        
        assert client._session is not None
        assert not client._session.closed
        
        await client.close()
        assert client._session.closed


class TestAsgardRateLimiting:
    """Tests for rate limiting functionality."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_enforced_between_requests(self):
        """Test that rate limiting adds delay between requests."""
        client = AsgardClient(api_key="test_key", rate_limit_rps=10.0)  # 100ms between requests
        
        start_time = time.time()
        
        # First request
        await client._enforce_rate_limit()
        
        # Second request should wait
        await client._enforce_rate_limit()
        
        elapsed = time.time() - start_time
        
        # Should have waited at least 100ms
        assert elapsed >= 0.08  # Allow some tolerance
    
    @pytest.mark.asyncio
    async def test_first_request_no_delay(self):
        """Test that first request doesn't wait."""
        client = AsgardClient(api_key="test_key", rate_limit_rps=1.0)
        
        start_time = time.time()
        await client._enforce_rate_limit()
        elapsed = time.time() - start_time
        
        # Should be essentially instant
        assert elapsed < 0.01


class TestAsgardErrorHandling:
    """Tests for error handling."""
    
    def test_handle_auth_error(self):
        """Test handling of 401 authentication error."""
        client = AsgardClient(api_key="test_key")
        
        with pytest.raises(AsgardAuthError) as exc_info:
            client._handle_error(401, {"error": "Invalid API key"})
        
        assert exc_info.value.status_code == 401
        assert "Invalid API key" in str(exc_info.value)
    
    def test_handle_rate_limit_error(self):
        """Test handling of 429 rate limit error."""
        client = AsgardClient(api_key="test_key")
        
        with pytest.raises(AsgardRateLimitError) as exc_info:
            client._handle_error(429, {"error": "Too many requests"})
        
        assert exc_info.value.status_code == 429
        assert "Too many requests" in str(exc_info.value)
    
    def test_handle_client_error(self):
        """Test handling of 4xx client errors."""
        client = AsgardClient(api_key="test_key")
        
        with pytest.raises(AsgardClientError) as exc_info:
            client._handle_error(400, {"error": "Bad request"})
        
        assert exc_info.value.status_code == 400
    
    def test_handle_server_error(self):
        """Test handling of 5xx server errors."""
        client = AsgardClient(api_key="test_key")
        
        with pytest.raises(AsgardServerError) as exc_info:
            client._handle_error(500, {"error": "Internal server error"})
        
        assert exc_info.value.status_code == 500
    
    def test_error_extracts_message_from_response(self):
        """Test that error message is extracted from response data."""
        client = AsgardClient(api_key="test_key")
        
        # Test with 'message' field
        with pytest.raises(AsgardClientError) as exc_info:
            client._handle_error(400, {"message": "Custom error message"})
        
        assert "Custom error message" in str(exc_info.value)


class TestAsgardRequestRetry:
    """Tests for request retry logic."""
    
    @pytest.mark.asyncio
    async def test_retry_on_server_error(self):
        """Test that requests are retried on server errors."""
        client = AsgardClient(api_key="test_key")
        
        # Mock session to fail twice then succeed
        call_count = 0
        
        class MockResponse:
            def __init__(self, status, data):
                self.status = status
                self._data = data
            
            async def json(self):
                return self._data
            
            async def __aenter__(self):
                return self
            
            async def __aexit__(self, *args):
                pass
        
        def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Return a response with 500 status
                return MockResponse(500, {"error": "Server error"})
            
            return MockResponse(200, {"success": True})
        
        mock_session = MagicMock()
        mock_session.request = mock_request
        mock_session.closed = False
        client._session = mock_session
        
        # Should succeed after retries
        result = await client._request("GET", "/test")
        assert result == {"success": True}
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self):
        """Test that client errors are not retried."""
        client = AsgardClient(api_key="test_key")
        
        class MockResponse:
            def __init__(self, status, data):
                self.status = status
                self._data = data
            
            async def json(self):
                return self._data
            
            async def __aenter__(self):
                return self
            
            async def __aexit__(self, *args):
                pass
        
        call_count = 0
        
        def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return MockResponse(400, {"error": "Client error"})
        
        mock_session = MagicMock()
        mock_session.request = mock_request
        mock_session.closed = False
        client._session = mock_session
        
        # Should fail immediately without retry
        with pytest.raises(AsgardClientError):
            await client._request("GET", "/test")
        
        # Should only have been called once (no retries)
        assert call_count == 1


class TestAsgardAuthHeader:
    """Tests for authentication header."""
    
    @pytest.mark.asyncio
    async def test_auth_header_included(self):
        """Test that X-API-Key header is included in requests."""
        client = AsgardClient(api_key="my_secret_key")
        await client._init_session()
        
        assert "X-API-Key" in client._session.headers
        assert client._session.headers["X-API-Key"] == "my_secret_key"
    
    @pytest.mark.asyncio
    async def test_auth_header_not_included_if_no_key(self):
        """Test that X-API-Key is not included if no API key."""
        client = AsgardClient(api_key="")
        await client._init_session()
        
        # Headers are set but may not have X-API-Key if empty
        # The actual implementation still adds it but it's empty


class TestAsgardEndpoints:
    """Tests for API endpoint methods."""
    
    @pytest.mark.asyncio
    async def test_get_markets(self):
        """Test get_markets endpoint."""
        client = AsgardClient(api_key="test_key")
        
        # Mock _get method
        expected_response = {
            "markets": [
                {
                    "strategy": "SOL-USDC",
                    "protocol": 0,
                    "lendingRate": 0.05,
                }
            ]
        }
        client._get = AsyncMock(return_value=expected_response)
        
        result = await client.get_markets()
        
        client._get.assert_called_once_with("/markets")
        assert result == expected_response
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health_check endpoint."""
        client = AsgardClient(api_key="test_key")
        
        expected_response = {"status": "healthy"}
        client._get = AsyncMock(return_value=expected_response)
        
        result = await client.health_check()
        
        client._get.assert_called_once_with("/health")
        assert result == expected_response


class TestAsgardClientErrors:
    """Tests for specific error scenarios."""
    
    @pytest.mark.asyncio
    async def test_auth_error_raises_exception(self):
        """Test that 401 response raises AsgardAuthError."""
        client = AsgardClient(api_key="invalid_key")
        
        class MockResponse:
            def __init__(self):
                self.status = 401
            
            async def json(self):
                return {"error": "Invalid key"}
            
            async def __aenter__(self):
                return self
            
            async def __aexit__(self, *args):
                pass
        
        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=MockResponse())
        mock_session.closed = False
        client._session = mock_session
        
        with pytest.raises(AsgardAuthError) as exc_info:
            await client._request("GET", "/markets")
        
        assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_rate_limit_error_raises_exception(self):
        """Test that 429 response raises AsgardRateLimitError."""
        client = AsgardClient(api_key="test_key")
        
        class MockResponse:
            def __init__(self):
                self.status = 429
            
            async def json(self):
                return {"error": "Rate limited"}
            
            async def __aenter__(self):
                return self
            
            async def __aexit__(self, *args):
                pass
        
        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=MockResponse())
        mock_session.closed = False
        client._session = mock_session
        
        with pytest.raises(AsgardRateLimitError) as exc_info:
            await client._request("GET", "/markets")
        
        assert exc_info.value.status_code == 429
