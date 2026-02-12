"""
Tests for dashboard bot bridge module.
"""
import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal
from datetime import datetime

import httpx

from backend.dashboard.bot_bridge import BotBridge, BotUnavailableError
from shared.common.schemas import BotStats, PositionSummary, PositionDetail, PauseState, PauseScope


class TestBotBridgeInitialization:
    """Tests for BotBridge initialization."""
    
    def test_default_initialization(self):
        """Test BotBridge with default parameters."""
        bridge = BotBridge()
        
        assert bridge._api_url == "http://bot:8000"
        assert bridge._internal_token is None
        assert bridge._cache_ttl == 5.0
        assert bridge._background_task is None
    
    def test_custom_initialization(self):
        """Test BotBridge with custom parameters."""
        bridge = BotBridge(
            bot_api_url="http://custom:9000",
            internal_token="secret_token"
        )
        
        assert bridge._api_url == "http://custom:9000"
        assert bridge._internal_token == "secret_token"


class TestBotBridgeCache:
    """Tests for BotBridge caching functionality."""
    
    def test_is_cache_fresh_true(self):
        """Test cache freshness when recent."""
        bridge = BotBridge()
        bridge._cache_timestamp["test_key"] = time.time()
        
        assert bridge._is_cache_fresh("test_key") is True
    
    def test_is_cache_fresh_false(self):
        """Test cache freshness when expired."""
        bridge = BotBridge()
        bridge._cache_timestamp["test_key"] = time.time() - 10.0  # 10 seconds ago
        
        assert bridge._is_cache_fresh("test_key") is False
    
    def test_is_cache_fresh_missing(self):
        """Test cache freshness when key doesn't exist."""
        bridge = BotBridge()
        
        assert bridge._is_cache_fresh("missing_key") is False
    
    def test_get_cached_fresh(self):
        """Test getting fresh cached value."""
        bridge = BotBridge()
        bridge._cache["test_key"] = "cached_value"
        bridge._cache_timestamp["test_key"] = time.time()
        
        result = bridge._get_cached("test_key")
        
        assert result == "cached_value"
    
    def test_get_cached_expired(self):
        """Test getting expired cached value returns None."""
        bridge = BotBridge()
        bridge._cache["test_key"] = "cached_value"
        bridge._cache_timestamp["test_key"] = time.time() - 10.0
        
        result = bridge._get_cached("test_key")
        
        assert result is None
    
    def test_set_cached(self):
        """Test setting cached value."""
        bridge = BotBridge()
        
        bridge._set_cached("test_key", "new_value")
        
        assert bridge._cache["test_key"] == "new_value"
        assert "test_key" in bridge._cache_timestamp
    
    def test_invalidate_cache_specific_key(self):
        """Test invalidating specific cache key."""
        bridge = BotBridge()
        bridge._cache_timestamp["key1"] = time.time()
        bridge._cache_timestamp["key2"] = time.time()
        
        bridge.invalidate_cache("key1")
        
        assert "key1" not in bridge._cache_timestamp
        assert "key2" in bridge._cache_timestamp
    
    def test_invalidate_cache_all(self):
        """Test invalidating all cache."""
        bridge = BotBridge()
        bridge._cache_timestamp["key1"] = time.time()
        bridge._cache_timestamp["key2"] = time.time()
        
        bridge.invalidate_cache()
        
        assert bridge._cache_timestamp == {}


class TestBotBridgeLifecycle:
    """Tests for BotBridge start/stop lifecycle."""
    
    @pytest.mark.asyncio
    async def test_start_creates_background_task(self):
        """Test start creates background refresh task."""
        bridge = BotBridge()
        
        with patch.object(bridge, '_background_refresh'):
            await bridge.start()
            
            assert bridge._background_task is not None
            assert not bridge._background_task.done()
        
        # Cleanup
        bridge._background_task.cancel()
        try:
            await bridge._background_task
        except asyncio.CancelledError:
            pass
    
    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        """Test stop cancels background task."""
        bridge = BotBridge()
        
        with patch.object(bridge, '_background_refresh', side_effect=asyncio.CancelledError):
            await bridge.start()
            
            with patch.object(bridge._client, 'aclose', new_callable=AsyncMock):
                await bridge.stop()
            
            assert bridge._background_task is None or bridge._background_task.done()
    
    @pytest.mark.asyncio
    async def test_stop_without_task(self):
        """Test stop when no background task exists."""
        bridge = BotBridge()
        
        with patch.object(bridge._client, 'aclose', new_callable=AsyncMock):
            await bridge.stop()  # Should not raise


class TestBotBridgeRequest:
    """Tests for BotBridge request methods."""
    
    @pytest.mark.asyncio
    async def test_request_success(self):
        """Test successful request."""
        bridge = BotBridge(internal_token="test_token")
        
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(bridge._client, 'request', new_callable=AsyncMock, return_value=mock_response):
            response = await bridge._request("GET", "/test")
            
            assert response == mock_response
    
    @pytest.mark.asyncio
    async def test_request_connect_error(self):
        """Test request with connection error."""
        bridge = BotBridge()
        
        with patch.object(bridge._client, 'request', side_effect=httpx.ConnectError("Connection refused")):
            with pytest.raises(BotUnavailableError):
                await bridge._request("GET", "/test")
    
    @pytest.mark.asyncio
    async def test_request_timeout(self):
        """Test request with timeout."""
        bridge = BotBridge()
        
        with patch.object(bridge._client, 'request', side_effect=httpx.TimeoutException("Timeout")):
            with pytest.raises(BotUnavailableError):
                await bridge._request("GET", "/test")
    
    @pytest.mark.asyncio
    async def test_request_adds_auth_header(self):
        """Test request includes authorization header."""
        bridge = BotBridge(internal_token="secret123")
        
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(bridge._client, 'request', new_callable=AsyncMock, return_value=mock_response) as mock_request:
            await bridge._request("GET", "/test")
            
            call_args = mock_request.call_args
            assert call_args[1]["headers"]["Authorization"] == "Bearer secret123"


class TestGetPositions:
    """Tests for get_positions method."""
    
    @pytest.mark.asyncio
    async def test_get_positions_from_cache(self):
        """Test getting positions from fresh cache."""
        bridge = BotBridge()
        
        cached_positions = {
            "pos1": PositionSummary(
                position_id="pos1",
                asset="SOL",
                status="open",
                leverage=Decimal("3.0"),
                deployed_usd=Decimal("10000"),
                long_value_usd=Decimal("10000"),
                short_value_usd=Decimal("30000"),
                delta=Decimal("100"),
                delta_ratio=Decimal("0.01"),
                asgard_hf=Decimal("1.2"),
                hyperliquid_mf=Decimal("0.15"),
                total_pnl_usd=Decimal("50"),
                funding_pnl_usd=Decimal("30"),
                opened_at=datetime.utcnow(),
                hold_duration_hours=24.5
            )
        }
        bridge._set_cached("positions_all", cached_positions)

        result = await bridge.get_positions()

        assert result == cached_positions
    
    @pytest.mark.asyncio
    async def test_get_positions_from_api(self):
        """Test fetching positions from API."""
        bridge = BotBridge()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "pos1": {
                "position_id": "pos1",
                "asset": "SOL",
                "status": "open",
                "leverage": "3.0",
                "deployed_usd": "10000",
                "long_value_usd": "10000",
                "short_value_usd": "30000",
                "delta": "100",
                "delta_ratio": "0.01",
                "asgard_hf": "1.2",
                "hyperliquid_mf": "0.15",
                "total_pnl_usd": "50",
                "funding_pnl_usd": "30",
                "opened_at": datetime.utcnow().isoformat(),
                "hold_duration_hours": 24.5
            }
        }
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            result = await bridge.get_positions()
            
            assert "pos1" in result
            assert result["pos1"].asset == "SOL"
    
    @pytest.mark.asyncio
    async def test_get_positions_timeout_with_stale_cache(self):
        """Test timeout falls back to stale cache."""
        bridge = BotBridge()
        
        # Set stale cache
        stale_positions = {"pos1": MagicMock()}
        bridge._cache["positions_all"] = stale_positions
        bridge._cache_timestamp["positions_all"] = time.time() - 10.0  # Expired

        with patch.object(bridge, '_request', side_effect=asyncio.TimeoutError):
            result = await bridge.get_positions()

            assert result == stale_positions
    
    @pytest.mark.asyncio
    async def test_get_positions_timeout_no_cache(self):
        """Test timeout with no cache raises error."""
        bridge = BotBridge()
        
        with patch.object(bridge, '_request', side_effect=asyncio.TimeoutError):
            with pytest.raises(BotUnavailableError):
                await bridge.get_positions()
    
    @pytest.mark.asyncio
    async def test_get_positions_bot_unavailable_with_stale_cache(self):
        """Test bot unavailable falls back to stale cache."""
        bridge = BotBridge()
        
        stale_positions = {"pos1": MagicMock()}
        bridge._cache["positions_all"] = stale_positions
        bridge._cache_timestamp["positions_all"] = time.time() - 10.0

        with patch.object(bridge, '_request', side_effect=BotUnavailableError("Bot down")):
            result = await bridge.get_positions()

            assert result == stale_positions


class TestGetPositionDetail:
    """Tests for get_position_detail method."""
    
    @pytest.mark.asyncio
    async def test_get_position_detail_from_cache(self):
        """Test getting position detail from cache."""
        bridge = BotBridge()
        
        cached_detail = PositionDetail(
            position_id="pos1",
            asset="SOL",
            status="open",
            leverage=Decimal("3.0"),
            deployed_usd=Decimal("10000"),
            long_value_usd=Decimal("10000"),
            short_value_usd=Decimal("30000"),
            delta=Decimal("100"),
            delta_ratio=Decimal("0.01"),
            asgard_hf=Decimal("1.2"),
            hyperliquid_mf=Decimal("0.15"),
            total_pnl_usd=Decimal("50"),
            funding_pnl_usd=Decimal("30"),
            opened_at=datetime.utcnow(),
            hold_duration_hours=24.5,
            sizing={},
            asgard={},
            hyperliquid={},
            pnl={},
            risk={}
        )
        bridge._set_cached("position_detail_pos1", cached_detail)
        
        result = await bridge.get_position_detail("pos1")
        
        assert result == cached_detail
    
    @pytest.mark.asyncio
    async def test_get_position_detail_from_api(self):
        """Test fetching position detail from API."""
        bridge = BotBridge()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "position_id": "pos1",
            "asset": "SOL",
            "status": "open",
            "leverage": "3.0",
            "deployed_usd": "10000",
            "long_value_usd": "10000",
            "short_value_usd": "30000",
            "delta": "100",
            "delta_ratio": "0.01",
            "asgard_hf": "1.2",
            "hyperliquid_mf": "0.15",
            "total_pnl_usd": "50",
            "funding_pnl_usd": "30",
            "opened_at": datetime.utcnow().isoformat(),
            "hold_duration_hours": 24.5,
            "sizing": {},
            "asgard": {},
            "hyperliquid": {},
            "pnl": {},
            "risk": {}
        }
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            result = await bridge.get_position_detail("pos1")
            
            assert result.position_id == "pos1"
            assert result.asset == "SOL"


class TestGetStats:
    """Tests for get_stats method."""
    
    @pytest.mark.asyncio
    async def test_get_stats_from_cache(self):
        """Test getting stats from cache."""
        bridge = BotBridge()
        
        cached_stats = BotStats(
            uptime_seconds=3600,
            uptime_formatted="1h 0m",
            opportunities_found=10,
            positions_opened=5,
            positions_closed=3,
            errors_count=0
        )
        bridge._set_cached("stats", cached_stats)
        
        result = await bridge.get_stats()
        
        assert result == cached_stats
    
    @pytest.mark.asyncio
    async def test_get_stats_from_api(self):
        """Test fetching stats from API."""
        bridge = BotBridge()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "uptime_seconds": 7200,
            "uptime_formatted": "2h 0m",
            "opportunities_found": 20,
            "positions_opened": 8,
            "positions_closed": 5,
            "errors_count": 1
        }
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            result = await bridge.get_stats()
            
            assert result.uptime_seconds == 7200
            assert result.opportunities_found == 20


class TestGetPauseState:
    """Tests for get_pause_state method."""
    
    @pytest.mark.asyncio
    async def test_get_pause_state_from_cache(self):
        """Test getting pause state from cache."""
        bridge = BotBridge()
        
        cached_state = PauseState(
            paused=True,
            scope=PauseScope.ENTRY,
            reason="Maintenance",
            paused_at=datetime.utcnow(),
            paused_by="admin",
            active_breakers=["circuit_breaker"]
        )
        bridge._set_cached("pause_state", cached_state)
        
        result = await bridge.get_pause_state()
        
        assert result == cached_state
    
    @pytest.mark.asyncio
    async def test_get_pause_state_from_api(self):
        """Test fetching pause state from API."""
        bridge = BotBridge()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "paused": False,
            "scope": "all",
            "reason": None,
            "paused_at": None,
            "paused_by": None,
            "active_breakers": []
        }
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            result = await bridge.get_pause_state()
            
            assert result.paused is False
            assert result.scope == PauseScope.ALL


class TestControlOperations:
    """Tests for pause/resume operations."""
    
    @pytest.mark.asyncio
    async def test_pause_success(self):
        """Test successful pause operation."""
        bridge = BotBridge()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            result = await bridge.pause("api_key", "Testing", "all")
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_pause_failure(self):
        """Test pause operation failure."""
        bridge = BotBridge()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False}
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            result = await bridge.pause("api_key", "Testing", "all")
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_pause_invalidates_cache(self):
        """Test pause invalidates pause_state cache."""
        bridge = BotBridge()
        bridge._cache_timestamp["pause_state"] = time.time()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            await bridge.pause("api_key", "Testing", "all")
            
            assert "pause_state" not in bridge._cache_timestamp
    
    @pytest.mark.asyncio
    async def test_resume_success(self):
        """Test successful resume operation."""
        bridge = BotBridge()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            result = await bridge.resume("api_key")
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_resume_invalidates_cache(self):
        """Test resume invalidates pause_state cache."""
        bridge = BotBridge()
        bridge._cache_timestamp["pause_state"] = time.time()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            await bridge.resume("api_key")
            
            assert "pause_state" not in bridge._cache_timestamp


class TestOpenPosition:
    """Tests for open_position method."""
    
    @pytest.mark.asyncio
    async def test_open_position_success(self):
        """Test successful position open."""
        bridge = BotBridge()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "position_id": "pos123"
        }
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            result = await bridge.open_position("SOL", 3.0, 10000)
            
            assert result["success"] is True
            assert result["position_id"] == "pos123"
    
    @pytest.mark.asyncio
    async def test_open_position_with_protocol(self):
        """Test opening position with specific protocol."""
        bridge = BotBridge()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response) as mock_request:
            await bridge.open_position("SOL", 3.0, 10000, protocol="kamino")
            
            call_args = mock_request.call_args
            assert call_args[1]["json"]["protocol"] == "kamino"
    
    @pytest.mark.asyncio
    async def test_open_position_invalidates_cache(self):
        """Test open position invalidates positions cache on success."""
        bridge = BotBridge()
        bridge._cache_timestamp["positions"] = time.time()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            await bridge.open_position("SOL", 3.0, 10000)
            
            assert "positions" not in bridge._cache_timestamp
    
    @pytest.mark.asyncio
    async def test_open_position_no_invalidation_on_failure(self):
        """Test open position doesn't invalidate cache on failure."""
        bridge = BotBridge()
        bridge._cache_timestamp["positions"] = time.time()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False}
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            await bridge.open_position("SOL", 3.0, 10000)
            
            assert "positions" in bridge._cache_timestamp


class TestHealthCheck:
    """Tests for health_check method."""
    
    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Test health check when bot is healthy."""
        bridge = BotBridge()
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(bridge._client, 'get', new_callable=AsyncMock, return_value=mock_response):
            result = await bridge.health_check()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """Test health check when bot returns error."""
        bridge = BotBridge()
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        
        with patch.object(bridge._client, 'get', new_callable=AsyncMock, return_value=mock_response):
            result = await bridge.health_check()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_health_check_exception(self):
        """Test health check when exception occurs."""
        bridge = BotBridge()
        
        with patch.object(bridge._client, 'get', side_effect=Exception("Connection error")):
            result = await bridge.health_check()
            
            assert result is False


class TestBotUnavailableError:
    """Tests for BotUnavailableError exception."""
    
    def test_exception_creation(self):
        """Test creating exception."""
        error = BotUnavailableError("Bot is down")
        
        assert str(error) == "Bot is down"
        assert isinstance(error, Exception)
