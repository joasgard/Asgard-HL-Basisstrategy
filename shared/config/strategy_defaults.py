"""Default strategy configuration values (7.1.4).

Zero-config start: a user who enables the bot without changing any settings
gets a conservative strategy. These defaults mirror the DB column defaults in
migration 014 and are used by the API when no row exists for a user.

System hard caps (from 7.3.4) are enforced at both save time and execution time.
"""
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StrategyDefaults:
    """Immutable default values for user_strategy_config."""

    enabled: bool = False

    # Assets
    assets: List[str] = field(default_factory=lambda: ["SOL"])
    protocols: Optional[List[str]] = None  # None = any available

    # Entry thresholds
    min_carry_apy: float = 15.0
    min_funding_rate_8hr: float = 0.005
    max_funding_volatility: float = 0.5

    # Position sizing
    max_position_pct: float = 0.25
    max_concurrent_positions: int = 2
    max_leverage: float = 3.0

    # Exit thresholds
    min_exit_carry_apy: float = 5.0
    take_profit_pct: Optional[float] = None  # disabled
    stop_loss_pct: float = 10.0

    # Recurse
    auto_reopen: bool = True
    cooldown_minutes: int = 30


DEFAULTS = StrategyDefaults()


# ---------------------------------------------------------------------------
# System hard caps (7.3.4) — override user settings at save + execution
# ---------------------------------------------------------------------------

SYSTEM_MIN_COOLDOWN_MINUTES = 5
SYSTEM_MAX_POSITIONS = 3
SYSTEM_MIN_POSITION_USD = 100.0
SYSTEM_MAX_POSITION_USD = 50_000.0
SYSTEM_MAX_LEVERAGE = 5.0
SYSTEM_MIN_STOP_LOSS_PCT = 1.0  # can't set stop-loss below 1%

# ---------------------------------------------------------------------------
# Risk engine limits (7.3.1–7.3.4)
# ---------------------------------------------------------------------------

RISK_MAX_DRAWDOWN_PCT = 20.0       # pause user if balance drops 20% from peak
RISK_MAX_DAILY_TRADES = 20         # max trades per user per day
RISK_CIRCUIT_BREAKER_FAILURES = 3  # pause after N consecutive execution failures


def to_dict(defaults: StrategyDefaults = DEFAULTS) -> dict:
    """Convert defaults to a dict suitable for API responses."""
    return {
        "enabled": defaults.enabled,
        "assets": list(defaults.assets),
        "protocols": defaults.protocols,
        "min_carry_apy": defaults.min_carry_apy,
        "min_funding_rate_8hr": defaults.min_funding_rate_8hr,
        "max_funding_volatility": defaults.max_funding_volatility,
        "max_position_pct": defaults.max_position_pct,
        "max_concurrent_positions": defaults.max_concurrent_positions,
        "max_leverage": defaults.max_leverage,
        "min_exit_carry_apy": defaults.min_exit_carry_apy,
        "take_profit_pct": defaults.take_profit_pct,
        "stop_loss_pct": defaults.stop_loss_pct,
        "auto_reopen": defaults.auto_reopen,
        "cooldown_minutes": defaults.cooldown_minutes,
    }
