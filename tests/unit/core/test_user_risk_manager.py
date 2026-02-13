"""Tests for UserRiskManager (7.3.1–7.3.5)."""
import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

from bot.core.user_risk_manager import UserRiskManager


USER_A = "did:privy:user_a"


def _mock_db():
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.execute = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# 7.3.1: Drawdown tracking
# ---------------------------------------------------------------------------

class TestDrawdown:
    @pytest.mark.asyncio
    async def test_first_check_initialises_peak(self):
        db = _mock_db()
        db.fetchone = AsyncMock(return_value=None)
        mgr = UserRiskManager(db)

        ok = await mgr.check_drawdown(USER_A, 1000.0)
        assert ok is True
        # Should have inserted a risk row
        assert db.execute.called

    @pytest.mark.asyncio
    async def test_new_high_updates_peak(self):
        db = _mock_db()
        db.fetchone = AsyncMock(return_value={"peak_balance_usd": 1000})
        mgr = UserRiskManager(db)

        ok = await mgr.check_drawdown(USER_A, 1200.0)
        assert ok is True
        # Should update peak
        calls = [str(c) for c in db.execute.call_args_list]
        assert any("peak_balance_usd" in c for c in calls)

    @pytest.mark.asyncio
    async def test_within_drawdown_limit(self):
        db = _mock_db()
        db.fetchone = AsyncMock(return_value={"peak_balance_usd": 1000})
        mgr = UserRiskManager(db)

        # 15% drawdown (under 20% limit)
        ok = await mgr.check_drawdown(USER_A, 850.0)
        assert ok is True

    @pytest.mark.asyncio
    async def test_exceeds_drawdown_limit_pauses_user(self):
        db = _mock_db()
        db.fetchone = AsyncMock(return_value={"peak_balance_usd": 1000})
        mgr = UserRiskManager(db)

        # 25% drawdown (over 20% limit)
        ok = await mgr.check_drawdown(USER_A, 750.0)
        assert ok is False
        # Should have paused via user_strategy_config
        calls = [str(c) for c in db.execute.call_args_list]
        assert any("paused_at" in c for c in calls)

    @pytest.mark.asyncio
    async def test_deposit_raises_peak(self):
        db = _mock_db()
        mgr = UserRiskManager(db)

        await mgr.update_peak_on_deposit(USER_A, 500.0)
        calls = [str(c) for c in db.execute.call_args_list]
        assert any("peak_balance_usd" in c and "+" in c for c in calls)

    @pytest.mark.asyncio
    async def test_withdrawal_reduces_peak_proportionally(self):
        db = _mock_db()
        mgr = UserRiskManager(db)

        # Withdraw from $9k to $5k → ratio = 5/9
        await mgr.update_peak_on_withdrawal(USER_A, 9000.0, 5000.0)
        calls = [str(c) for c in db.execute.call_args_list]
        assert any("peak_balance_usd" in c for c in calls)

    @pytest.mark.asyncio
    async def test_withdrawal_zero_balance_before(self):
        db = _mock_db()
        mgr = UserRiskManager(db)

        # Edge case: balance_before = 0 → skip update
        await mgr.update_peak_on_withdrawal(USER_A, 0, 0)
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# 7.3.2: Daily trade limit
# ---------------------------------------------------------------------------

class TestDailyTradeLimit:
    @pytest.mark.asyncio
    async def test_no_record_means_under_limit(self):
        db = _mock_db()
        db.fetchone = AsyncMock(return_value=None)
        mgr = UserRiskManager(db)

        assert await mgr.check_daily_trade_limit(USER_A) is True

    @pytest.mark.asyncio
    async def test_under_limit(self):
        db = _mock_db()
        db.fetchone = AsyncMock(return_value={
            "daily_trade_count": 5,
            "daily_trade_date": date.today(),
        })
        mgr = UserRiskManager(db)

        assert await mgr.check_daily_trade_limit(USER_A) is True

    @pytest.mark.asyncio
    async def test_at_limit(self):
        db = _mock_db()
        db.fetchone = AsyncMock(return_value={
            "daily_trade_count": 20,
            "daily_trade_date": date.today(),
        })
        mgr = UserRiskManager(db)

        assert await mgr.check_daily_trade_limit(USER_A) is False

    @pytest.mark.asyncio
    async def test_new_day_resets_count(self):
        db = _mock_db()
        db.fetchone = AsyncMock(return_value={
            "daily_trade_count": 20,
            "daily_trade_date": date(2025, 1, 1),  # old date
        })
        mgr = UserRiskManager(db)

        assert await mgr.check_daily_trade_limit(USER_A) is True

    @pytest.mark.asyncio
    async def test_record_trade_increments_count(self):
        db = _mock_db()
        # First call: upsert check
        db.fetchone = AsyncMock(side_effect=[
            {"user_id": USER_A},  # existing row
        ])
        mgr = UserRiskManager(db)

        await mgr.record_trade(USER_A)
        calls = [str(c) for c in db.execute.call_args_list]
        assert any("daily_trade_count" in c for c in calls)


# ---------------------------------------------------------------------------
# 7.3.3: Consecutive failure circuit breaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_single_failure_stays_active(self):
        db = _mock_db()
        db.fetchone = AsyncMock(side_effect=[
            {"user_id": USER_A},  # upsert check
            {"consecutive_failures": 1},  # after increment
        ])
        mgr = UserRiskManager(db)

        ok = await mgr.record_failure(USER_A, "test error")
        assert ok is True

    @pytest.mark.asyncio
    async def test_three_failures_trips_breaker(self):
        db = _mock_db()
        db.fetchone = AsyncMock(side_effect=[
            {"user_id": USER_A},  # upsert check
            {"consecutive_failures": 3},  # after increment = threshold
        ])
        mgr = UserRiskManager(db)

        ok = await mgr.record_failure(USER_A, "third failure")
        assert ok is False
        # Should have paused
        calls = [str(c) for c in db.execute.call_args_list]
        assert any("paused_at" in c for c in calls)
        assert any("circuit_breaker" in c for c in calls)

    @pytest.mark.asyncio
    async def test_success_resets_failures(self):
        db = _mock_db()
        db.fetchone = AsyncMock(return_value={"user_id": USER_A})
        mgr = UserRiskManager(db)

        await mgr.record_success(USER_A)
        calls = [str(c) for c in db.execute.call_args_list]
        assert any("consecutive_failures = 0" in c for c in calls)


# ---------------------------------------------------------------------------
# 7.3.5: Risk status for dashboard
# ---------------------------------------------------------------------------

class TestRiskStatus:
    @pytest.mark.asyncio
    async def test_no_record_returns_defaults(self):
        db = _mock_db()
        db.fetchone = AsyncMock(return_value=None)
        mgr = UserRiskManager(db)

        status = await mgr.get_risk_status(USER_A)
        assert status["drawdown_pct"] == 0.0
        assert status["daily_trades"] == 0
        assert status["consecutive_failures"] == 0

    @pytest.mark.asyncio
    async def test_with_data(self):
        db = _mock_db()
        db.fetchone = AsyncMock(return_value={
            "peak_balance_usd": 10000,
            "current_balance_usd": 8500,
            "daily_trade_count": 3,
            "daily_trade_date": date.today(),
            "consecutive_failures": 1,
            "last_failure_reason": "timeout",
        })
        mgr = UserRiskManager(db)

        status = await mgr.get_risk_status(USER_A)
        assert status["drawdown_pct"] == 15.0
        assert status["peak_balance_usd"] == 10000.0
        assert status["daily_trades"] == 3
        assert status["consecutive_failures"] == 1
        assert status["last_failure_reason"] == "timeout"
