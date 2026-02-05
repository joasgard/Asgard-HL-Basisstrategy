"""
BasisStrategy trading bot.

A sophisticated basis trading system for DeFi protocols.
"""

__version__ = "1.0.0"

# Re-export main classes
from src.core.bot import DeltaNeutralBot, BotConfig, BotStats

__all__ = ["DeltaNeutralBot", "BotConfig", "BotStats"]
