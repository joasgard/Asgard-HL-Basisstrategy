"""
Structured JSON logging configuration using structlog.
"""
import logging
import sys

import structlog
from structlog.types import FilteringBoundLogger

from src.config.settings import get_settings


def get_logger(name: str) -> FilteringBoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
