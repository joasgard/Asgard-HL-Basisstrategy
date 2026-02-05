"""Tests for BotBridge."""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.dashboard.bot_bridge import BotBridge, BotUnavailableError
from src.shared.schemas import PositionSummary, BotStats, PauseState


class TestBotBridgeCache:
    """Test BotBridge caching behavior."""
    
    @pytest.fixture
    def bridge(self):
        """Create a BotBridge instance."""
        return BotBridge(
            bot_api_url="http://test:8000",
            internal_token="test_token"
        )
    
    @pytest.fixture
    def mock_positions_data(self):
        """Mock positions data."""
        return {
            "pos_001": {
                "position_id": "pos_001",
                "asset": "SOL",
                "status": "open",
                "leverage": "2.5",
                "deployed_usd": "1000.00",
                "long_value_usd": "1000.00",
                "short_value_usd": "1000.00",
                "delta": "0.00",
                "delta_ratio": "0.0001",
                "asgard_hf": "1.5",
                "hyperliquid_mf": "0.1",
                "total_pnl_usd": "10.50",
                "funding_pnl_usd": "5.25",
                "opened_at": datetime.utcnow().isoformat(),
                "hold_duration_hours": 24.5,
            }
        }
    
    @pytest.fixture
    def mock_stats_data(self):
        """Mock stats data."""
        return {
            "uptime_seconds": 3600.0,
            "uptime_formatted": "01:00:00",
            "opportunities_found": 100,
            "positions_opened": 10,
            "positions_closed": 5,
            "errors_count": 2,
        }
    
    @pytest.mark.asyncio
    async def test_get_positions_returns_fresh_data(self, bridge, mock_positions_data):
        """Test that get_positions fetches and caches fresh data."""
        mock_response = MagicMock()
        mock_response.json.return_value = mock_positions_data
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            positions = await bridge.get_positions()
            
            assert "pos_001" in positions
            assert positions["pos_001"].asset == "SOL"
            assert positions["pos_001"].leverage == Decimal("2.5")
    
    @pytest.mark.asyncio
    async def test_get_positions_returns_cached_data(self, bridge, mock_positions_data):
        """Test that fresh cached data is returned without API call."""
        # Pre-populate cache
        bridge._cache["positions"] = {
            "pos_001": PositionSummary(
                position_id="pos_001",
                asset="SOL",
                status="open",
                leverage=Decimal("2.5"),
                deployed_usd=Decimal("1000.00"),
                long_value_usd=Decimal("1000.00"),
                short_value_usd=Decimal("1000.00"),
                delta=Decimal("0.00"),
                delta_ratio=Decimal("0.0001"),
                asgard_hf=Decimal("1.5"),
                hyperliquid_mf=Decimal("0.1"),
                total_pnl_usd=Decimal("10.50"),
                funding_pnl_usd=Decimal("5.25"),
                opened_at=datetime.utcnow(),
                hold_duration_hours=24.5,
            )
        }
        bridge._cache_timestamp["positions"] = time.time()
        
        # Should not make API call
        with patch.object(bridge, '_request') as mock_request:
            positions = await bridge.get_positions()
            mock_request.assert_not_called()
            assert "pos_001" in positions
    
    @pytest.mark.asyncio
    async def test_get_positions_returns_stale_on_timeout(self, bridge, mock_positions_data):
        """Test that stale data is returned on timeout."""
        import time
        
        # Pre-populate stale cache (older than 5 seconds)
        bridge._cache["positions"] = {
            "pos_001": PositionSummary(
                position_id="pos_001",
                asset="SOL",
                status="open",
                leverage=Decimal("2.5"),
                deployed_usd=Decimal("1000.00"),
                long_value_usd=Decimal("1000.00"),
                short_value_usd=Decimal("1000.00"),
                delta=Decimal("0.00"),
                delta_ratio=Decimal("0.0001"),
                asgard_hf=Decimal("1.5"),
                hyperliquid_mf=Decimal("0.1"),
                total_pnl_usd=Decimal("10.50"),
                funding_pnl_usd=Decimal("5.25"),
                opened_at=datetime.utcnow(),
                hold_duration_hours=24.5,
            )
        }
        bridge._cache_timestamp["positions"] = time.time() - 10  # 10 seconds old
        
        # Simulate timeout
        async def slow_request(*args, **kwargs):
            await asyncio.sleep(3)  # Longer than 2s timeout
            return MagicMock()
        
        with patch.object(bridge, '_request', side_effect=slow_request):
            positions = await bridge.get_positions()
            # Should return stale cache
            assert "pos_001" in positions
    
    @pytest.mark.asyncio
    async def test_get_positions_raises_when_no_cache_and_bot_down(self, bridge):
        """Test that exception is raised when no cache and bot unavailable."""
        with patch.object(bridge, '_request', side_effect=BotUnavailableError("Bot down")):
            with pytest.raises(BotUnavailableError):
                await bridge.get_positions()
    
    @pytest.mark.asyncio
    async def test_get_stats_with_caching(self, bridge, mock_stats_data):
        """Test that get_stats uses caching."""
        mock_response = MagicMock()
        mock_response.json.return_value = mock_stats_data
        
        with patch.object(bridge, '_request', new_callable=AsyncMock, return_value=mock_response):
            # First call should hit API
            stats1 = await bridge.get_stats()
            assert stats1.uptime_seconds == 3600.0
            
            # Second call should use cache
            stats2 = await bridge.get_stats()
            assert bridge._request.call_count == 1  # Only called once


class TestBotBridgeBackgroundRefresh:
    """Test background refresh functionality."""
    
    @pytest.mark.asyncio
    async def test_background_refresh_keeps_cache_warm(self):
        """Test that background refresh keeps cache warm."""
        bridge = BotBridge(
            bot_api_url="http://test:8000",
            internal_token="test_token"
        )
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "pos_001": {
                "position_id": "pos_001",
                "asset": "SOL",
                "status": "open",
                "leverage": "2.5",
                "deployed_usd": "1000.00",
                "long_value_usd": "1000.00",
                "short_value_usd": "1000.00",
                "delta": "0.00",
                "delta_ratio": "0.0001",
                "asgard_hf": "1.5",
                "hyperliquid_mf": "0.1",
                "total_pnl_usd": "10.50",
                "funding_pnl_usd": "5.25",
                "opened_at": datetime.utcnow().isoformat(),
                "hold_duration_hours": 24.5,
            }
        }
        
        call_count = 0
        
        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_response
        
        with patch.object(bridge, '_request', side_effect=mock_request):
            # Start background refresh
            await bridge.start()
            
            # Wait for at least one background refresh
            await asyncio.sleep(0.1)  # Let it start
            
            # Cancel the task
            if bridge._background_task:
                bridge._background_task.cancel()
                try:
                    await bridge._background_task
                except asyncio.CancelledError:
                    pass
        
        await bridge.stop()


class TestBotBridgeHealthCheck:
    """Test health check functionality."""
    
    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_healthy(self):
        """Test health check returns True when bot is healthy."""
        bridge = BotBridge(
            bot_api_url="http://test:8000",
            internal_token="test_token"
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(bridge._client, 'get', new_callable=AsyncMock, return_value=mock_response):
            is_healthy = await bridge.health_check()
            assert is_healthy is True
        
        await bridge.stop()
    
    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_error(self):
        """Test health check returns False on error."""
        bridge = BotBridge(
            bot_api_url="http://test:8000",
            internal_token="test_token"
        )
        
        with patch.object(bridge._client, 'get', side_effect=Exception("Connection failed")):
            is_healthy = await bridge.health_check()
            assert is_healthy is False
        
        await bridge.stop()


class TestBotBridgeCacheInvalidation:
    """Test cache invalidation."""
    
    def test_invalidate_specific_key(self):
        """Test invalidating a specific cache key."""
        bridge = BotBridge()
        
        # Populate cache
        bridge._cache["positions"] = {"test": "data"}
        bridge._cache_timestamp["positions"] = time.time()
        bridge._cache["stats"] = {"test": "data"}
        bridge._cache_timestamp["stats"] = time.time()
        
        # Invalidate only positions
        bridge.invalidate_cache("positions")
        
        assert "positions" not in bridge._cache_timestamp
        assert "stats" in bridge._cache_timestamp
    
    def test_invalidate_all_cache(self):
        """Test invalidating all cache."""
        bridge = BotBridge()
        
        # Populate cache
        bridge._cache_timestamp["positions"] = time.time()
        bridge._cache_timestamp["stats"] = time.time()
        bridge._cache_timestamp["pause_state"] = time.time()
        
        # Invalidate all
        bridge.invalidate_cache()
        
        assert len(bridge._cache_timestamp) == 0


import time
