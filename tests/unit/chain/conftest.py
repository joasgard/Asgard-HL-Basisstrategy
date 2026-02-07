"""
Pytest configuration for chain tests.

This module patches the retry configuration to disable retries during tests,
preventing long wait times when tests fail.
"""
import pytest
from unittest.mock import patch

# Store original retry config
_original_retry_config = None


@pytest.fixture(autouse=True, scope="session")
def disable_retries():
    """
    Disable RPC retries for all chain tests.
    
    This prevents tests from hanging when mocked RPC calls fail.
    """
    import src.utils.retry as retry_module
    from src.utils.retry import RetryConfig
    
    # Save original
    original_rpc_retry = retry_module.RPC_RETRY
    
    # Create test config with no retries and no wait
    test_config = RetryConfig(
        max_attempts=1,  # No retries
        wait_strategy="fixed",
        wait_fixed_seconds=0,  # No wait
        retry_exceptions=(Exception,),
        log_before_sleep=False,  # Disable sleep logging
    )
    
    # Patch the module
    retry_module.RPC_RETRY = test_config
    
    yield
    
    # Restore original
    retry_module.RPC_RETRY = original_rpc_retry
