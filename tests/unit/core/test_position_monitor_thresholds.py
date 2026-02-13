"""Tests for per-user exit thresholds in PositionMonitor (7.2.4)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from bot.core.position_monitor import PositionMonitorService
from bot.core.risk_engine import ExitReason


def _make_monitor():
    db = AsyncMock()
    monitor = PositionMonitorService(db=db)
    return monitor


# ---------------------------------------------------------------------------
# Stop-loss (7.2.4)
# ---------------------------------------------------------------------------

class TestStopLoss:
    def test_stop_loss_triggered(self):
        monitor = _make_monitor()
        data = {"total_pnl": -120, "size_usd": 1000}
        config = {"stop_loss_pct": 10.0, "take_profit_pct": None, "min_exit_carry_apy": None}

        result = monitor._check_user_exit_thresholds(data, config, None)
        assert result is not None
        assert result.should_exit is True
        assert result.reason == ExitReason.STOP_LOSS
        assert result.details["pnl_pct"] == -12.0

    def test_stop_loss_not_triggered(self):
        monitor = _make_monitor()
        data = {"total_pnl": -50, "size_usd": 1000}
        config = {"stop_loss_pct": 10.0, "take_profit_pct": None, "min_exit_carry_apy": None}

        result = monitor._check_user_exit_thresholds(data, config, None)
        assert result is None

    def test_stop_loss_exactly_at_threshold(self):
        monitor = _make_monitor()
        data = {"total_pnl": -100, "size_usd": 1000}
        config = {"stop_loss_pct": 10.0, "take_profit_pct": None, "min_exit_carry_apy": None}

        result = monitor._check_user_exit_thresholds(data, config, None)
        assert result is not None
        assert result.reason == ExitReason.STOP_LOSS

    def test_stop_loss_no_size_skips(self):
        """If no size_usd, can't compute P&L pct → skip."""
        monitor = _make_monitor()
        data = {"total_pnl": -500}
        config = {"stop_loss_pct": 10.0, "take_profit_pct": None, "min_exit_carry_apy": None}

        result = monitor._check_user_exit_thresholds(data, config, None)
        assert result is None

    def test_stop_loss_none_skips(self):
        """If stop_loss_pct is None, skip check."""
        monitor = _make_monitor()
        data = {"total_pnl": -500, "size_usd": 1000}
        config = {"stop_loss_pct": None, "take_profit_pct": None, "min_exit_carry_apy": None}

        result = monitor._check_user_exit_thresholds(data, config, None)
        assert result is None


# ---------------------------------------------------------------------------
# Take-profit (7.2.4)
# ---------------------------------------------------------------------------

class TestTakeProfit:
    def test_take_profit_triggered(self):
        monitor = _make_monitor()
        data = {"total_pnl": 250, "size_usd": 1000}
        config = {"stop_loss_pct": 10.0, "take_profit_pct": 20.0, "min_exit_carry_apy": None}

        result = monitor._check_user_exit_thresholds(data, config, None)
        assert result is not None
        assert result.reason == ExitReason.TARGET_PROFIT
        assert result.details["pnl_pct"] == 25.0

    def test_take_profit_not_triggered(self):
        monitor = _make_monitor()
        data = {"total_pnl": 100, "size_usd": 1000}
        config = {"stop_loss_pct": 10.0, "take_profit_pct": 20.0, "min_exit_carry_apy": None}

        result = monitor._check_user_exit_thresholds(data, config, None)
        assert result is None

    def test_take_profit_disabled(self):
        monitor = _make_monitor()
        data = {"total_pnl": 999, "size_usd": 100}
        config = {"stop_loss_pct": 10.0, "take_profit_pct": None, "min_exit_carry_apy": None}

        result = monitor._check_user_exit_thresholds(data, config, None)
        assert result is None


# ---------------------------------------------------------------------------
# Min exit carry APY (7.2.4)
# ---------------------------------------------------------------------------

class TestMinExitCarryAPY:
    def test_carry_dropped_below_threshold(self):
        monitor = _make_monitor()
        # funding rate -0.0001 → carry = 0.0001 * 3 * 365 * 3.0 * 100 = 32.85%
        data = {"leverage": 3.0}
        config = {"stop_loss_pct": None, "take_profit_pct": None, "min_exit_carry_apy": 50.0}

        result = monitor._check_user_exit_thresholds(data, config, -0.0001)
        assert result is not None
        assert result.reason == ExitReason.NEGATIVE_APY
        assert result.details["current_carry_apy"] < 50.0

    def test_carry_above_threshold(self):
        monitor = _make_monitor()
        # funding rate -0.01 → carry = 0.01 * 3 * 365 * 3.0 * 100 = 3285%
        data = {"leverage": 3.0}
        config = {"stop_loss_pct": None, "take_profit_pct": None, "min_exit_carry_apy": 50.0}

        result = monitor._check_user_exit_thresholds(data, config, -0.01)
        assert result is None

    def test_funding_flipped_positive_triggers(self):
        monitor = _make_monitor()
        data = {"leverage": 3.0}
        config = {"stop_loss_pct": None, "take_profit_pct": None, "min_exit_carry_apy": 5.0}

        result = monitor._check_user_exit_thresholds(data, config, 0.001)
        assert result is not None
        assert result.reason == ExitReason.NEGATIVE_APY

    def test_no_funding_data_skips(self):
        monitor = _make_monitor()
        data = {"leverage": 3.0}
        config = {"stop_loss_pct": None, "take_profit_pct": None, "min_exit_carry_apy": 5.0}

        result = monitor._check_user_exit_thresholds(data, config, None)
        assert result is None

    def test_min_exit_carry_none_skips(self):
        monitor = _make_monitor()
        data = {"leverage": 3.0}
        config = {"stop_loss_pct": None, "take_profit_pct": None, "min_exit_carry_apy": None}

        result = monitor._check_user_exit_thresholds(data, config, -0.0001)
        assert result is None


# ---------------------------------------------------------------------------
# Priority: stop-loss fires before take-profit
# ---------------------------------------------------------------------------

class TestThresholdPriority:
    def test_stop_loss_takes_priority(self):
        """If both stop-loss and take-profit could fire, stop-loss wins."""
        monitor = _make_monitor()
        # Negative P&L: -15%
        data = {"total_pnl": -150, "size_usd": 1000}
        config = {"stop_loss_pct": 10.0, "take_profit_pct": 5.0, "min_exit_carry_apy": None}

        result = monitor._check_user_exit_thresholds(data, config, None)
        assert result.reason == ExitReason.STOP_LOSS
