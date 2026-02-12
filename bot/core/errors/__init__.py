"""
Error handling system for Asgard Basis.

Provides structured error codes and messages for both API and frontend consumption.
"""

from .codes import ErrorCode, ErrorCategory, get_error_info, get_error_description
from .exceptions import (
    AsgardError,
    ValidationError,
    InsufficientFundsError,
    HyperliquidError,
    PositionError,
    RiskError,
    NetworkError,
    AuthError,
)
from .handlers import register_exception_handlers

__all__ = [
    # Codes
    "ErrorCode",
    "ErrorCategory",
    "get_error_info",
    "get_error_description",
    # Exceptions
    "AsgardError",
    "ValidationError",
    "InsufficientFundsError",
    "HyperliquidError",
    "PositionError",
    "RiskError",
    "NetworkError",
    "AuthError",
    # Handlers
    "register_exception_handlers",
]
