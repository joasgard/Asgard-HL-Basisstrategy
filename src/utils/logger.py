"""
Structured JSON logging configuration using structlog.
"""
import logging
import sys
from typing import Any, Dict

import structlog
from structlog.types import FilteringBoundLogger

from src.config.settings import get_settings


def configure_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> FilteringBoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class LogContext:
    """Context manager for adding structured context to logs."""
    
    def __init__(self, **context: Any):
        self.context = context
        self.logger = structlog.get_logger()
    
    def __enter__(self) -> FilteringBoundLogger:
        self.logger = self.logger.bind(**self.context)
        return self.logger
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        # Unbind context (structlog handles this automatically with bind)
        pass


def log_opportunity(
    logger: FilteringBoundLogger,
    asset: str,
    protocol: str,
    funding_rate: float,
    net_carry_apy: float,
    total_apy: float,
    size_usd: float,
) -> None:
    """Log opportunity detection with consistent format."""
    logger.info(
        "opportunity_detected",
        asset=asset,
        protocol=protocol,
        funding_rate_apy=funding_rate,
        net_carry_apy=net_carry_apy,
        total_apy=total_apy,
        size_usd=size_usd,
    )


def log_position_event(
    logger: FilteringBoundLogger,
    event: str,
    position_id: str,
    asset: str,
    side: str,
    size_usd: float,
    leverage: float,
    **extra: Any,
) -> None:
    """Log position lifecycle events."""
    logger.info(
        f"position_{event}",
        position_id=position_id,
        asset=asset,
        side=side,
        size_usd=size_usd,
        leverage=leverage,
        **extra,
    )


def log_risk_event(
    logger: FilteringBoundLogger,
    risk_type: str,
    severity: str,  # "warning", "critical", "emergency"
    message: str,
    **extra: Any,
) -> None:
    """Log risk-related events with severity."""
    log_func = {
        "warning": logger.warning,
        "critical": logger.error,
        "emergency": logger.critical,
    }.get(severity, logger.warning)
    
    log_func(
        "risk_event",
        risk_type=risk_type,
        severity=severity,
        message=message,
        **extra,
    )
