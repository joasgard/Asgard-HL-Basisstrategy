"""
Tests for Hyperliquid API Client.

These tests verify:
- Client initialization
- Info endpoint calls
- Exchange endpoint calls
- Error handling
- Retry logic
"""
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from src.venues.hyperliquid.client import (
    HyperliquidClient,
    HyperliquidAPIError,
    HyperliquidAuthError,
    HyperliquidRateLimitError,
    HyperliquidClientError,
    HyperliquidServerError,
)


class TestHyperliquidClientInit:
    """Tests for client initialization."""
    
    def test_init_with_default_url(self):
        """Test initialization with default API URL."""
        client = HyperliquidClient()
        assert client.base_url == HyperliquidClient.API_BASE
    
    def test_init_with_custom_url(self):
        """Test initialization with custom API URL."""
        client = HyperliquidClient(base_url="https://custom.hyperliquid.xyz")
        assert client.base_url == "https://custom.hyperliquid.xyz"


class TestHyperliquidClientContextManager:
    """Tests for async context manager."""
    
    @pytest.mark.asyncio
    async def test_context_manager_initializes_session(self):
        """Test that context manager initializes and closes session."""
        async with HyperliquidClient() as client:
            assert client._session is not None
            assert not client._session.closed
        
        # Session should be closed after exiting context
        assert client._session.closed
    
    @pytest.mark.asyncio
    async def test_manual_close(self):
        """Test manual session close."""
        client = HyperliquidClient()
        await client._init_session()
        
        assert client._session is not None
        assert not client._session.closed
        
        await client.close()
        assert client._session.closed


class TestHyperliquidErrorHandling:
    """Tests for error handling."""
    
    def test_handle_auth_error(self):
        """Test handling of authentication error."""
        client = HyperliquidClient()
        
        with pytest.raises(HyperliquidAuthError) as exc_info:
            client._handle_error(401, {"error": "Invalid signature"})
        
        assert exc_info.value.status_code == 401
        assert "Invalid signature" in str(exc_info.value)
    
    def test_handle_auth_error_from_message(self):
        """Test auth error detected from message content."""
        client = HyperliquidClient()
        
        with pytest.raises(HyperliquidAuthError) as exc_info:
            client._handle_error(200, {"error": "signature verification failed"})
        
        # Note: This would actually pass through _request and check response body
        # The _handle_error checks status code, but _request also checks for "status": "err"
    
    def test_handle_rate_limit_error(self):
        """Test handling of rate limit error."""
        client = HyperliquidClient()
        
        with pytest.raises(HyperliquidRateLimitError) as exc_info:
            client._handle_error(429, {"error": "Too many requests"})
        
        assert exc_info.value.status_code == 429
    
    def test_handle_client_error(self):
        """Test handling of 4xx client errors."""
        client = HyperliquidClient()
        
        with pytest.raises(HyperliquidClientError) as exc_info:
            client._handle_error(400, {"error": "Bad request"})
        
        assert exc_info.value.status_code == 400
    
    def test_handle_server_error(self):
        """Test handling of 5xx server errors."""
        client = HyperliquidClient()
        
        with pytest.raises(HyperliquidServerError) as exc_info:
            client._handle_error(500, {"error": "Internal server error"})
        
        assert exc_info.value.status_code == 500


class TestHyperliquidInfoEndpoint:
    """Tests for info endpoint methods."""
    
    @pytest.mark.asyncio
    async def test_info_endpoint(self):
        """Test basic info endpoint call."""
        client = HyperliquidClient()
        
        expected_response = {"fundingRates": [{"coin": "SOL", "fundingRate": 0.0001}]}
        client._request = AsyncMock(return_value=expected_response)
        
        result = await client.info({"type": "fundingRates"})
        
        client._request.assert_called_once_with("/info", {"type": "fundingRates"})
        assert result == expected_response
    
    @pytest.mark.asyncio
    async def test_get_meta_and_asset_contexts(self):
        """Test getting meta and asset contexts."""
        client = HyperliquidClient()
        
        expected = {
            "meta": {"universe": [{"name": "SOL", "maxLeverage": 50}]},
            "assetCtxs": [{"coin": "SOL", "markPx": 100.0}]
        }
        client.info = AsyncMock(return_value=expected)
        
        result = await client.get_meta_and_asset_contexts()
        
        client.info.assert_called_once_with({"type": "metaAndAssetCtxs"})
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_clearinghouse_state(self):
        """Test getting clearinghouse state."""
        client = HyperliquidClient()
        
        expected = {
            "assetPositions": [],
            "marginSummary": {"accountValue": "1000.0"}
        }
        client.info = AsyncMock(return_value=expected)
        
        result = await client.get_clearinghouse_state("0x123abc")
        
        client.info.assert_called_once_with({
            "type": "clearinghouseState",
            "user": "0x123abc",
        })
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_funding_history(self):
        """Test getting funding history."""
        client = HyperliquidClient()
        
        expected = [
            {"coin": "SOL", "fundingRate": 0.0001, "time": 1700000000000}
        ]
        client.info = AsyncMock(return_value=expected)
        
        result = await client.get_funding_history("SOL", 1700000000000)
        
        client.info.assert_called_once_with({
            "type": "fundingHistory",
            "coin": "SOL",
            "startTime": 1700000000000,
        })
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_funding_history_with_end_time(self):
        """Test getting funding history with end time."""
        client = HyperliquidClient()
        
        client.info = AsyncMock(return_value=[])
        
        await client.get_funding_history("SOL", 1700000000000, 1700086400000)
        
        client.info.assert_called_once_with({
            "type": "fundingHistory",
            "coin": "SOL",
            "startTime": 1700000000000,
            "endTime": 1700086400000,
        })
    
    @pytest.mark.asyncio
    async def test_get_l2_book(self):
        """Test getting L2 order book."""
        client = HyperliquidClient()
        
        expected = {"coin": "SOL", "levels": [[100.0, 1.0], [101.0, 2.0]]}
        client.info = AsyncMock(return_value=expected)
        
        result = await client.get_l2_book("SOL")
        
        client.info.assert_called_once_with({"type": "l2Book", "coin": "SOL"})
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_all_mids(self):
        """Test getting all mid prices."""
        client = HyperliquidClient()
        
        expected = {"SOL": 100.0, "ETH": 2000.0}
        client.info = AsyncMock(return_value=expected)
        
        result = await client.get_all_mids()
        
        client.info.assert_called_once_with({"type": "allMids"})
        assert result == expected


class TestHyperliquidExchangeEndpoint:
    """Tests for exchange endpoint."""
    
    @pytest.mark.asyncio
    async def test_exchange_endpoint(self):
        """Test basic exchange endpoint call."""
        client = HyperliquidClient()
        
        expected_response = {"status": "ok", "response": {"type": "order"}}
        client._request = AsyncMock(return_value=expected_response)
        
        signed_payload = {
            "action": {"type": "order", "orders": []},
            "nonce": 123456,
            "signature": "0xabc123",
        }
        result = await client.exchange(signed_payload)
        
        client._request.assert_called_once_with("/exchange", signed_payload)
        assert result == expected_response


class TestHyperliquidRetryLogic:
    """Tests for retry behavior."""
    
    @pytest.mark.asyncio
    async def test_retry_on_server_error(self):
        """Test that requests are retried on server errors."""
        client = HyperliquidClient()
        
        # Mock to fail twice then succeed
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
        
        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return MockResponse(500, {"error": "Server error"})
            return MockResponse(200, {"status": "ok"})
        
        mock_session = MagicMock()
        mock_session.post = mock_post
        mock_session.closed = False
        client._session = mock_session
        
        # Should succeed after retries
        result = await client._request("/info", {"type": "test"})
        assert result == {"status": "ok"}
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self):
        """Test that client errors are not retried."""
        client = HyperliquidClient()
        
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
        
        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return MockResponse(400, {"error": "Bad request"})
        
        mock_session = MagicMock()
        mock_session.post = mock_post
        mock_session.closed = False
        client._session = mock_session
        
        # Should fail immediately without retry
        with pytest.raises(HyperliquidClientError):
            await client._request("/info", {"type": "test"})
        
        # Should only have been called once (no retries)
        assert call_count == 1


class TestHyperliquidAPIErrorInResponse:
    """Tests for error responses in 200 OK body."""
    
    @pytest.mark.asyncio
    async def test_error_in_response_body(self):
        """Test handling of errors in 200 response body."""
        client = HyperliquidClient()
        
        # Create mock response class with proper async context manager
        class MockResponse:
            status = 200
            
            async def json(self):
                return {"status": "err", "response": "Invalid order"}
            
            async def __aenter__(self):
                return self
            
            async def __aexit__(self, *args):
                return None
        
        mock_session = MagicMock()
        mock_session.post = lambda *args, **kwargs: MockResponse()
        mock_session.closed = False
        client._session = mock_session
        
        with pytest.raises(HyperliquidClientError) as exc_info:
            await client._request("/exchange", {"action": {}})
        
        assert "Invalid order" in str(exc_info.value)
