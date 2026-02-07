"""
Retry utilities using tenacity.
"""
import logging
from typing import Any, Callable, TypeVar, Tuple, Optional

from tenacity import (
    retry as tenacity_retry,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    wait_fixed,
    retry_if_exception_type,
    before_sleep_log,
)

from src.utils.logger import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        max_delay_seconds: Optional[float] = None,
        wait_strategy: str = "exponential",  # "exponential" or "fixed"
        wait_min: float = 1.0,
        wait_max: float = 60.0,
        wait_fixed_seconds: float = 2.0,
        retry_exceptions: Tuple[type, ...] = (Exception,),
        log_before_sleep: bool = True,
    ):
        self.max_attempts = max_attempts
        self.max_delay_seconds = max_delay_seconds
        self.wait_strategy = wait_strategy
        self.wait_min = wait_min
        self.wait_max = wait_max
        self.wait_fixed_seconds = wait_fixed_seconds
        self.retry_exceptions = retry_exceptions
        self.log_before_sleep = log_before_sleep


def _get_stop_condition(config: RetryConfig):
    """Build stop condition from config."""
    stops = [stop_after_attempt(config.max_attempts)]
    if config.max_delay_seconds:
        stops.append(stop_after_delay(config.max_delay_seconds))
    
    # Combine with OR logic (stop when any condition met)
    from tenacity.stop import stop_any
    return stop_any(*stops)


def _get_wait_strategy(config: RetryConfig):
    """Build wait strategy from config."""
    if config.wait_strategy == "fixed":
        return wait_fixed(config.wait_fixed_seconds)
    else:
        return wait_exponential(
            multiplier=1,
            min=config.wait_min,
            max=config.wait_max,
        )


def retry(
    max_attempts: int = 3,
    max_delay_seconds: Optional[float] = None,
    wait_strategy: str = "exponential",
    wait_min: float = 1.0,
    wait_max: float = 60.0,
    wait_fixed_seconds: float = 2.0,
    retry_exceptions: Tuple[type, ...] = (Exception,),
    log_before_sleep: bool = True,
) -> Callable[[F], F]:
    """
    Decorator for retrying function calls with configurable strategy.
    
    Args:
        max_attempts: Maximum number of retry attempts
        max_delay_seconds: Maximum total time to retry (None = no limit)
        wait_strategy: "exponential" or "fixed"
        wait_min: Minimum wait time (exponential strategy)
        wait_max: Maximum wait time (exponential strategy)
        wait_fixed_seconds: Fixed wait time (fixed strategy)
        retry_exceptions: Tuple of exception types to retry on
        log_before_sleep: Whether to log before each retry
    
    Example:
        @retry(max_attempts=5, wait_strategy="fixed", wait_fixed_seconds=2.0)
        async def fetch_data():
            ...
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        max_delay_seconds=max_delay_seconds,
        wait_strategy=wait_strategy,
        wait_min=wait_min,
        wait_max=wait_max,
        wait_fixed_seconds=wait_fixed_seconds,
        retry_exceptions=retry_exceptions,
        log_before_sleep=log_before_sleep,
    )
    
    def decorator(func: F) -> F:
        retry_decorator = tenacity_retry(
            stop=_get_stop_condition(config),
            wait=_get_wait_strategy(config),
            retry=retry_if_exception_type(config.retry_exceptions),
            before_sleep=before_sleep_log(logger, logging.WARNING) if log_before_sleep else None,
            reraise=True,
        )
        return retry_decorator(func)
    
    return decorator


def retry_with_config(config: RetryConfig) -> Callable[[F], F]:
    """Retry decorator using a RetryConfig object."""
    def decorator(func: F) -> F:
        retry_decorator = tenacity_retry(
            stop=_get_stop_condition(config),
            wait=_get_wait_strategy(config),
            retry=retry_if_exception_type(config.retry_exceptions),
            before_sleep=before_sleep_log(logger, logging.WARNING) if config.log_before_sleep else None,
            reraise=True,
        )
        return retry_decorator(func)
    
    return decorator


# Predefined retry configurations for common scenarios

ASGARD_RETRY = RetryConfig(
    max_attempts=3,
    wait_strategy="exponential",
    wait_min=0.5,
    wait_max=5.0,
    retry_exceptions=(Exception,),
)

HYPERLIQUID_RETRY = RetryConfig(
    max_attempts=15,
    wait_strategy="fixed",
    wait_fixed_seconds=2.0,
    retry_exceptions=(Exception,),
)

RPC_RETRY = RetryConfig(
    max_attempts=5,
    wait_strategy="exponential",
    wait_min=0.5,
    wait_max=10.0,
    retry_exceptions=(Exception,),
)


def retry_rpc(func: F) -> F:
    """Retry configuration for RPC calls."""
    return retry_with_config(RPC_RETRY)(func)
