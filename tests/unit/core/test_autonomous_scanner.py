"""Tests for AutonomousScanner (7.2.1–7.2.5)."""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from bot.core.autonomous_scanner import AutonomousScanner


USER_A = "did:privy:user_a"
USER_B = "did:privy:user_b"


def _config_row(**overrides):
    row = {
        "user_id": USER_A,
        "min_carry_apy": 15.0,
        "min_funding_rate_8hr": 0.005,
        "max_funding_volatility": 0.5,
        "max_position_pct": 0.25,
        "max_concurrent_positions": 2,
        "max_leverage": 3.0,
        "min_exit_carry_apy": 5.0,
        "take_profit_pct": None,
        "stop_loss_pct": 10.0,
        "auto_reopen": True,
        "cooldown_minutes": 30,
        "last_close_time": None,
        "cooldown_at_close": None,
        "assets": ["SOL"],
    }
    row.update(overrides)
    return row


def _make_rate_info(rate_8hr: float):
    info = MagicMock()
    info.rate_8hr = rate_8hr
    return info


# ---------------------------------------------------------------------------
# Cooldown (7.2.2)
# ---------------------------------------------------------------------------

class TestCooldown:
    def test_no_last_close_means_no_cooldown(self):
        scanner = AutonomousScanner(db=AsyncMock())
        assert scanner._cooldown_elapsed(_config_row()) is True

    def test_cooldown_not_elapsed(self):
        scanner = AutonomousScanner(db=AsyncMock())
        config = _config_row(
            last_close_time=datetime.utcnow() - timedelta(minutes=10),
            cooldown_at_close=30,
        )
        assert scanner._cooldown_elapsed(config) is False

    def test_cooldown_elapsed(self):
        scanner = AutonomousScanner(db=AsyncMock())
        config = _config_row(
            last_close_time=datetime.utcnow() - timedelta(minutes=60),
            cooldown_at_close=30,
        )
        assert scanner._cooldown_elapsed(config) is True

    def test_cooldown_uses_value_at_close_not_current(self):
        """N6: cooldown_at_close prevents bypass via config update."""
        scanner = AutonomousScanner(db=AsyncMock())
        config = _config_row(
            last_close_time=datetime.utcnow() - timedelta(minutes=10),
            cooldown_minutes=5,  # user changed to 5 minutes after close
            cooldown_at_close=30,  # but at close time it was 30 minutes
        )
        assert scanner._cooldown_elapsed(config) is False

    def test_system_minimum_cooldown(self):
        """System minimum is 5 minutes even if user sets lower."""
        scanner = AutonomousScanner(db=AsyncMock())
        config = _config_row(
            last_close_time=datetime.utcnow() - timedelta(minutes=3),
            cooldown_at_close=1,  # below system min
        )
        # Should still be in cooldown (3 < 5 system min)
        assert scanner._cooldown_elapsed(config) is False


# ---------------------------------------------------------------------------
# Entry criteria (7.2.3)
# ---------------------------------------------------------------------------

class TestEntryCriteria:
    def test_positive_funding_rejected(self):
        scanner = AutonomousScanner(db=AsyncMock())
        result = scanner._check_entry_criteria(
            _config_row(), "SOL", _make_rate_info(0.001), {}
        )
        assert result["should_enter"] is False
        assert result["reason"] == "funding_positive"

    def test_funding_below_threshold(self):
        scanner = AutonomousScanner(db=AsyncMock())
        result = scanner._check_entry_criteria(
            _config_row(min_funding_rate_8hr=0.01),
            "SOL",
            _make_rate_info(-0.005),  # abs < threshold
            {"SOL": 0.3},
        )
        assert result["should_enter"] is False
        assert result["reason"] == "funding_below_threshold"

    def test_volatility_too_high(self):
        scanner = AutonomousScanner(db=AsyncMock())
        result = scanner._check_entry_criteria(
            _config_row(max_funding_volatility=0.3),
            "SOL",
            _make_rate_info(-0.01),
            {"SOL": 0.8},  # > 0.3
        )
        assert result["should_enter"] is False
        assert result["reason"] == "volatility_too_high"

    def test_carry_below_threshold(self):
        scanner = AutonomousScanner(db=AsyncMock())
        # rate -0.0001 passes funding threshold (set to 0.00005)
        # carry = 0.0001 * 3 * 365 * 3.0 * 100 = 32.85% < 50%
        result = scanner._check_entry_criteria(
            _config_row(min_carry_apy=50.0, min_funding_rate_8hr=0.00005),
            "SOL",
            _make_rate_info(-0.0001),
            {"SOL": 0.2},
        )
        assert result["should_enter"] is False
        assert result["reason"] == "carry_below_threshold"

    def test_all_criteria_pass(self):
        scanner = AutonomousScanner(db=AsyncMock())
        result = scanner._check_entry_criteria(
            _config_row(min_carry_apy=5.0, min_funding_rate_8hr=0.001),
            "SOL",
            _make_rate_info(-0.01),
            {"SOL": 0.2},
        )
        assert result["should_enter"] is True
        assert result["asset"] == "SOL"
        assert result["estimated_carry_apy"] > 0


# ---------------------------------------------------------------------------
# Per-user evaluation (7.2.1)
# ---------------------------------------------------------------------------

class TestEvaluateUser:
    @pytest.mark.asyncio
    async def test_skips_user_at_position_limit(self):
        db = AsyncMock()
        db.fetchone = AsyncMock(side_effect=[
            {"locked": True},  # advisory lock
            {"paused_at": None},  # not paused
            {"cnt": 2},  # at limit
        ])
        scanner = AutonomousScanner(db=db)
        config = _config_row(max_concurrent_positions=2)
        market = {"funding_rates": {"SOL": _make_rate_info(-0.01)}, "volatilities": {"SOL": 0.2}}

        # Should return without opening anything
        await scanner._evaluate_user(config, market)

    @pytest.mark.asyncio
    async def test_skips_user_in_cooldown(self):
        db = AsyncMock()
        db.fetchone = AsyncMock(side_effect=[
            {"locked": True},
        ])
        scanner = AutonomousScanner(db=db)
        config = _config_row(
            last_close_time=datetime.utcnow() - timedelta(minutes=5),
            cooldown_at_close=30,
        )
        market = {"funding_rates": {"SOL": _make_rate_info(-0.01)}, "volatilities": {"SOL": 0.2}}

        await scanner._evaluate_user(config, market)
        # No position opened, no DB queries beyond the lock

    @pytest.mark.asyncio
    async def test_skips_paused_user(self):
        db = AsyncMock()
        db.fetchone = AsyncMock(side_effect=[
            {"locked": True},  # advisory lock
            {"paused_at": datetime.utcnow()},  # paused!
        ])
        scanner = AutonomousScanner(db=db)
        config = _config_row()
        market = {"funding_rates": {"SOL": _make_rate_info(-0.01)}, "volatilities": {"SOL": 0.2}}

        await scanner._evaluate_user(config, market)

    @pytest.mark.asyncio
    async def test_skips_when_advisory_lock_held(self):
        """N11: PG advisory lock prevents concurrent evaluation."""
        db = AsyncMock()
        db.fetchone = AsyncMock(return_value={"locked": False})  # can't get lock
        scanner = AutonomousScanner(db=db)

        await scanner._evaluate_user(_config_row(), {})


# ---------------------------------------------------------------------------
# Scan cycle
# ---------------------------------------------------------------------------

class TestScanCycle:
    @pytest.mark.asyncio
    async def test_no_enabled_users_is_noop(self):
        db = AsyncMock()
        db.fetchall = AsyncMock(return_value=[])
        scanner = AutonomousScanner(db=db)

        with patch.object(scanner, "_fetch_market_data", return_value={"funding_rates": {}}):
            await scanner._scan_cycle()

    @pytest.mark.asyncio
    async def test_error_in_one_user_doesnt_stop_others(self):
        db = AsyncMock()
        db.fetchall = AsyncMock(return_value=[
            _config_row(user_id=USER_A),
            _config_row(user_id=USER_B),
        ])
        scanner = AutonomousScanner(db=db)

        users_evaluated = []

        async def mock_evaluate(user_row, market_data):
            users_evaluated.append(user_row["user_id"])
            if user_row["user_id"] == USER_A:
                raise RuntimeError("Boom")

        scanner._evaluate_user = mock_evaluate

        with patch.object(scanner, "_fetch_market_data", return_value={"funding_rates": {}}):
            await scanner._scan_cycle()

        assert USER_A in users_evaluated
        assert USER_B in users_evaluated
