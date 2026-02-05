"""Pytest configuration and fixtures for dashboard tests."""

import pytest
import asyncio
from typing import AsyncGenerator


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_client() -> AsyncGenerator:
    """Async HTTP client for testing."""
    import httpx
    async with httpx.AsyncClient() as client:
        yield client
