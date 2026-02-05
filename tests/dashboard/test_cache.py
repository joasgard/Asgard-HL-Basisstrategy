"""Tests for dashboard cache module."""

import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


# =============================================================================
# TimedCache Tests
# =============================================================================

class TestTimedCache:
    """Tests for TimedCache class."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache instance."""
        from dashboard.cache import TimedCache
        return TimedCache(ttl_seconds=0.1)  # Short TTL for tests

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        """Test basic set and get operations."""
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, cache):
        """Test getting a non-existent key."""
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_expired(self, cache):
        """Test that expired keys return None."""
        await cache.set("key1", "value1")
        
        # Wait for expiration
        await asyncio.sleep(0.15)
        
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_fresh(self, cache):
        """Test that fresh keys return value."""
        await cache.set("key1", "value1")
        
        # Should still be fresh
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_or_set_new_key(self, cache):
        """Test get_or_set with new key."""
        async def factory():
            return "computed_value"
        
        result = await cache.get_or_set("key1", factory)
        assert result == "computed_value"

    @pytest.mark.asyncio
    async def test_get_or_set_existing_key(self, cache):
        """Test get_or_set with existing key."""
        await cache.set("key1", "existing_value")
        
        async def factory():
            return "new_value"
        
        result = await cache.get_or_set("key1", factory)
        assert result == "existing_value"  # Should return cached value

    @pytest.mark.asyncio
    async def test_get_or_set_expired(self, cache):
        """Test get_or_set with expired key."""
        await cache.set("key1", "old_value")
        await asyncio.sleep(0.15)  # Wait for expiration
        
        async def factory():
            return "new_value"
        
        result = await cache.get_or_set("key1", factory)
        assert result == "new_value"  # Should call factory

    @pytest.mark.asyncio
    async def test_get_or_set_async_factory(self, cache):
        """Test get_or_set with async factory function."""
        async def async_factory():
            await asyncio.sleep(0.01)
            return "async_value"
        
        result = await cache.get_or_set("key1", async_factory)
        assert result == "async_value"

    @pytest.mark.asyncio
    async def test_invalidate_specific_key(self, cache):
        """Test invalidating a specific key."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        
        cache.invalidate("key1")
        
        # key1 should be gone
        result1 = await cache.get("key1")
        assert result1 is None
        
        # key2 should still exist
        result2 = await cache.get("key2")
        assert result2 == "value2"

    @pytest.mark.asyncio
    async def test_invalidate_all(self, cache):
        """Test invalidating all keys."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        
        cache.invalidate()
        
        # All keys should be gone
        result1 = await cache.get("key1")
        result2 = await cache.get("key2")
        assert result1 is None
        assert result2 is None

    @pytest.mark.asyncio
    async def test_concurrent_access(self, cache):
        """Test concurrent access to cache."""
        results = []
        
        async def setter(n):
            await cache.set(f"key{n}", f"value{n}")
            results.append(f"set{n}")
        
        async def getter(n):
            val = await cache.get(f"key{n}")
            results.append(f"get{n}:{val}")
        
        # Run setters and getters concurrently
        tasks = []
        for i in range(10):
            tasks.append(setter(i))
            tasks.append(getter(i))
        
        await asyncio.gather(*tasks)
        
        # All operations should complete without error
        assert len(results) == 20

    @pytest.mark.asyncio
    async def test_different_value_types(self, cache):
        """Test caching different value types."""
        # String
        await cache.set("str", "hello")
        assert await cache.get("str") == "hello"
        
        # Integer
        await cache.set("int", 42)
        assert await cache.get("int") == 42
        
        # List
        await cache.set("list", [1, 2, 3])
        assert await cache.get("list") == [1, 2, 3]
        
        # Dict
        await cache.set("dict", {"a": 1})
        assert await cache.get("dict") == {"a": 1}
        
        # None
        await cache.set("none", None)
        assert await cache.get("none") is None


# =============================================================================
# Cached Decorator Tests
# =============================================================================

class TestCachedDecorator:
    """Tests for @cached decorator."""

    @pytest.mark.asyncio
    async def test_cached_decorator_basic(self):
        """Test basic caching with decorator."""
        from dashboard.cache import cached
        
        call_count = 0
        
        @cached(ttl_seconds=1.0)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        # First call
        result1 = await expensive_function(5)
        assert result1 == 10
        assert call_count == 1
        
        # Second call with same arg - should use cache
        result2 = await expensive_function(5)
        assert result2 == 10
        assert call_count == 1  # Not incremented

    @pytest.mark.asyncio
    async def test_cached_decorator_different_args(self):
        """Test caching with different arguments."""
        from dashboard.cache import cached
        
        call_count = 0
        
        @cached(ttl_seconds=1.0)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        result1 = await expensive_function(5)
        result2 = await expensive_function(10)
        
        assert result1 == 10
        assert result2 == 20
        assert call_count == 2  # Called twice for different args

    @pytest.mark.asyncio
    async def test_cached_decorator_expiration(self):
        """Test that cached results expire."""
        from dashboard.cache import cached
        
        call_count = 0
        
        @cached(ttl_seconds=0.05)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        # First call
        await expensive_function(5)
        assert call_count == 1
        
        # Wait for expiration
        await asyncio.sleep(0.1)
        
        # Second call - should recalculate
        await expensive_function(5)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_cached_decorator_with_kwargs(self):
        """Test caching with keyword arguments."""
        from dashboard.cache import cached
        
        call_count = 0
        
        @cached(ttl_seconds=1.0)
        async def expensive_function(x, y=1):
            nonlocal call_count
            call_count += 1
            return x * y
        
        # Same result, different arg format - creates different cache keys
        result1 = await expensive_function(5, y=2)
        result2 = await expensive_function(x=5, y=2)
        
        assert result1 == result2
        # Called twice due to different cache keys (positional vs keyword)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_cached_decorator_cache_access(self):
        """Test accessing cache from decorated function."""
        from dashboard.cache import cached
        
        @cached(ttl_seconds=1.0)
        async def my_func(x):
            return x * 2
        
        await my_func(5)
        
        # Access the cache
        cached_value = await my_func.cache.get("my_func:5")
        assert cached_value == 10

    @pytest.mark.asyncio
    async def test_cached_decorator_invalidate(self):
        """Test invalidating cached results."""
        from dashboard.cache import cached
        
        call_count = 0
        
        @cached(ttl_seconds=1.0)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        await expensive_function(5)
        assert call_count == 1
        
        # Invalidate cache
        expensive_function.cache.invalidate()
        
        # Should recalculate
        await expensive_function(5)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_cached_decorator_preserves_function_name(self):
        """Test that decorator preserves function metadata."""
        from dashboard.cache import cached
        
        @cached(ttl_seconds=1.0)
        async def my_awesome_function(x):
            """My docstring."""
            return x * 2
        
        assert my_awesome_function.__name__ == "my_awesome_function"


# =============================================================================
# Integration Tests
# =============================================================================

class TestCacheIntegration:
    """Integration tests for cache module."""

    @pytest.mark.asyncio
    async def test_multiple_decorated_functions(self):
        """Test multiple functions with their own caches."""
        from dashboard.cache import cached
        
        count_a = 0
        count_b = 0
        
        @cached(ttl_seconds=1.0)
        async def func_a(x):
            nonlocal count_a
            count_a += 1
            return f"a-{x}"
        
        @cached(ttl_seconds=1.0)
        async def func_b(x):
            nonlocal count_b
            count_b += 1
            return f"b-{x}"
        
        # Call both functions
        assert await func_a(1) == "a-1"
        assert await func_b(1) == "b-1"
        assert count_a == 1
        assert count_b == 1
        
        # Call again - should use cache
        assert await func_a(1) == "a-1"
        assert await func_b(1) == "b-1"
        assert count_a == 1
        assert count_b == 1

    @pytest.mark.asyncio
    async def test_cache_isolation(self):
        """Test that different caches are isolated."""
        from dashboard.cache import cached
        
        @cached(ttl_seconds=1.0)
        async def func_a(x):
            return f"a-{x}"
        
        @cached(ttl_seconds=1.0)
        async def func_b(x):
            return f"b-{x}"
        
        await func_a(1)
        await func_b(1)
        
        # Each function should have its own cache
        cache_a = await func_a.cache.get("func_a:1")
        cache_b = await func_b.cache.get("func_b:1")
        
        assert cache_a == "a-1"
        assert cache_b == "b-1"

    @pytest.mark.asyncio
    async def test_high_load(self):
        """Test cache under high load."""
        from dashboard.cache import cached
        
        call_count = 0
        
        @cached(ttl_seconds=1.0)
        async def func(x):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate work
            return x * 2
        
        # Call same function many times concurrently
        # Note: Cache doesn't deduplicate concurrent calls, only caches completed results
        tasks = [func(5) for _ in range(100)]
        results = await asyncio.gather(*tasks)
        
        # All should return same result
        assert all(r == 10 for r in results)
        
        # Each concurrent call executes (no request deduplication)
        # But subsequent calls with same args use cache
        assert call_count >= 1
        
        # After all complete, cache should be warm
        call_count_after = call_count
        await func(5)
        assert call_count == call_count_after  # Should not increase
