"""
Tests for IntentScanner service.

These tests verify:
- Scanner lifecycle (start/stop)
- Intent processing: activation, expiry, criteria checking
- Funding rate criteria
- Funding volatility criteria
- Entry price criteria
- Execution flow
- Error handling
"""
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.core.intent_scanner import IntentScanner, _parse_datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_intent_row(
    intent_id="intent_1",
    user_id="user_1",
    asset="SOL",
    status="active",
    leverage=3.0,
    size_usd=1000.0,
    min_funding_rate=None,
    max_funding_volatility=0.50,
    max_entry_price=None,
    expires_at=None,
):
    """Create a fake DB row for an intent."""
    return {
        "id": intent_id,
        "user_id": user_id,
        "asset": asset,
        "leverage": leverage,
        "size_usd": size_usd,
        "min_funding_rate": min_funding_rate,
        "max_funding_volatility": max_funding_volatility,
        "max_entry_price": max_entry_price,
        "status": status,
        "position_id": None,
        "job_id": None,
        "execution_error": None,
        "criteria_snapshot": None,
        "expires_at": expires_at,
        "created_at": "2026-01-01T00:00:00",
        "activated_at": None,
        "executed_at": None,
        "cancelled_at": None,
    }


def _make_mock_db(rows=None):
    """Create a mock database."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=rows or [])
    db.fetchone = AsyncMock(return_value=None)
    db.execute = AsyncMock()

    # Mock transaction context manager
    mock_tx = AsyncMock()
    mock_tx.execute = AsyncMock()
    mock_tx.fetchone = AsyncMock(return_value=None)
    mock_tx.fetchall = AsyncMock(return_value=[])

    @asynccontextmanager
    async def mock_transaction():
        yield mock_tx

    db.transaction = mock_transaction
    db._mock_tx = mock_tx  # expose for assertions
    return db


def _make_scanner(db=None, rows=None):
    """Create an IntentScanner with mock DB."""
    return IntentScanner(db=db or _make_mock_db(rows))


# ---------------------------------------------------------------------------
# Lifecycle Tests
# ---------------------------------------------------------------------------


class TestScannerLifecycle:
    """Tests for start/stop behavior."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        scanner = _make_scanner()
        with patch.object(scanner, "_run_loop", new_callable=AsyncMock):
            await scanner.start()
            assert scanner._running is True
            assert scanner._task is not None
            await scanner.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        scanner = _make_scanner()
        with patch.object(scanner, "_run_loop", new_callable=AsyncMock):
            await scanner.start()
            await scanner.stop()
            assert scanner._running is False

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self):
        scanner = _make_scanner()
        with patch.object(scanner, "_run_loop", new_callable=AsyncMock):
            await scanner.start()
            first_task = scanner._task
            await scanner.start()
            assert scanner._task is first_task
            await scanner.stop()


# ---------------------------------------------------------------------------
# Scan Cycle Tests
# ---------------------------------------------------------------------------


class TestScanCycle:
    """Tests for the main scan cycle."""

    @pytest.mark.asyncio
    async def test_no_intents_is_noop(self):
        db = _make_mock_db(rows=[])
        scanner = _make_scanner(db=db)
        await scanner._scan_cycle()
        db.fetchall.assert_called_once()

    @pytest.mark.asyncio
    async def test_processes_all_intents(self):
        rows = [
            _make_intent_row("i1", "u1"),
            _make_intent_row("i2", "u2"),
        ]
        db = _make_mock_db(rows=rows)
        scanner = _make_scanner(db=db)

        with patch.object(scanner, "_process_intent", new_callable=AsyncMock) as mock_proc:
            await scanner._scan_cycle()
            assert mock_proc.call_count == 2

    @pytest.mark.asyncio
    async def test_intent_error_does_not_cascade(self):
        rows = [
            _make_intent_row("i1", "u1"),
            _make_intent_row("i2", "u2"),
        ]
        db = _make_mock_db(rows=rows)
        scanner = _make_scanner(db=db)

        call_count = 0

        async def side_effect(row, now):
            nonlocal call_count
            call_count += 1
            if row["id"] == "i1":
                raise RuntimeError("Error processing i1")

        with patch.object(scanner, "_process_intent", side_effect=side_effect):
            await scanner._scan_cycle()

        assert call_count == 2


# ---------------------------------------------------------------------------
# Intent Processing Tests
# ---------------------------------------------------------------------------


class TestProcessIntent:
    """Tests for individual intent processing."""

    @pytest.mark.asyncio
    async def test_expires_past_due_intent(self):
        db = _make_mock_db()
        scanner = _make_scanner(db=db)

        row = _make_intent_row(
            expires_at=(datetime.utcnow() - timedelta(hours=1)).isoformat()
        )
        now = datetime.utcnow()

        with patch.object(scanner, "_expire_intent", new_callable=AsyncMock) as mock_expire:
            await scanner._process_intent(row, now)
            mock_expire.assert_called_once_with("intent_1")

    @pytest.mark.asyncio
    async def test_activates_pending_intent(self):
        db = _make_mock_db()
        scanner = _make_scanner(db=db)

        row = _make_intent_row(status="pending")
        now = datetime.utcnow()

        with patch.object(scanner, "_check_criteria", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = {"all_passed": False, "checks": {}}
            await scanner._process_intent(row, now)

            # Should have updated status to 'active'
            activate_call = None
            for call in db.execute.call_args_list:
                if "status = 'active'" in str(call):
                    activate_call = call
                    break
            assert activate_call is not None

    @pytest.mark.asyncio
    async def test_executes_when_all_criteria_pass(self):
        db = _make_mock_db()
        scanner = _make_scanner(db=db)

        row = _make_intent_row(status="active")
        now = datetime.utcnow()

        criteria = {"all_passed": True, "checks": {"funding_rate": {"passed": True}}}

        with patch.object(scanner, "_check_criteria", new_callable=AsyncMock, return_value=criteria):
            with patch.object(scanner, "_execute_intent", new_callable=AsyncMock) as mock_exec:
                await scanner._process_intent(row, now)
                mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_execute_when_criteria_fail(self):
        db = _make_mock_db()
        scanner = _make_scanner(db=db)

        row = _make_intent_row(status="active")
        now = datetime.utcnow()

        criteria = {"all_passed": False, "checks": {"funding_rate": {"passed": False}}}

        with patch.object(scanner, "_check_criteria", new_callable=AsyncMock, return_value=criteria):
            with patch.object(scanner, "_execute_intent", new_callable=AsyncMock) as mock_exec:
                await scanner._process_intent(row, now)
                mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# Criteria Check Tests
# ---------------------------------------------------------------------------


class TestCheckFunding:
    """Tests for funding rate criteria."""

    @pytest.mark.asyncio
    async def test_passes_when_funding_negative(self):
        scanner = _make_scanner()
        oracle = MagicMock()

        rate_info = MagicMock()
        rate_info.funding_rate = -0.002
        oracle.get_current_funding_rates = AsyncMock(return_value={"SOL": rate_info})

        row = _make_intent_row(min_funding_rate=None)
        result = await scanner._check_funding(oracle, "SOL", row)
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_fails_when_funding_positive(self):
        scanner = _make_scanner()
        oracle = MagicMock()

        rate_info = MagicMock()
        rate_info.funding_rate = 0.001
        oracle.get_current_funding_rates = AsyncMock(return_value={"SOL": rate_info})

        row = _make_intent_row()
        result = await scanner._check_funding(oracle, "SOL", row)
        assert result["passed"] is False
        assert "non-negative" in result["reason"]

    @pytest.mark.asyncio
    async def test_fails_when_above_min_threshold(self):
        scanner = _make_scanner()
        oracle = MagicMock()

        rate_info = MagicMock()
        rate_info.funding_rate = -0.0005  # Only -0.05%
        oracle.get_current_funding_rates = AsyncMock(return_value={"SOL": rate_info})

        row = _make_intent_row(min_funding_rate=-0.001)  # Requires at least -0.1%
        result = await scanner._check_funding(oracle, "SOL", row)
        assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_passes_when_below_min_threshold(self):
        scanner = _make_scanner()
        oracle = MagicMock()

        rate_info = MagicMock()
        rate_info.funding_rate = -0.002  # -0.2%
        oracle.get_current_funding_rates = AsyncMock(return_value={"SOL": rate_info})

        row = _make_intent_row(min_funding_rate=-0.001)
        result = await scanner._check_funding(oracle, "SOL", row)
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_fails_when_no_data(self):
        scanner = _make_scanner()
        oracle = MagicMock()
        oracle.get_current_funding_rates = AsyncMock(return_value={})

        row = _make_intent_row()
        result = await scanner._check_funding(oracle, "SOL", row)
        assert result["passed"] is False


class TestCheckVolatility:
    """Tests for funding volatility criteria."""

    @pytest.mark.asyncio
    async def test_passes_when_below_max(self):
        scanner = _make_scanner()
        oracle = MagicMock()
        oracle.calculate_funding_volatility = AsyncMock(return_value=0.30)

        row = _make_intent_row(max_funding_volatility=0.50)
        result = await scanner._check_volatility(oracle, "SOL", row)
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_fails_when_above_max(self):
        scanner = _make_scanner()
        oracle = MagicMock()
        oracle.calculate_funding_volatility = AsyncMock(return_value=0.70)

        row = _make_intent_row(max_funding_volatility=0.50)
        result = await scanner._check_volatility(oracle, "SOL", row)
        assert result["passed"] is False


class TestCheckPrice:
    """Tests for entry price criteria."""

    @pytest.mark.asyncio
    async def test_passes_when_no_limit(self):
        scanner = _make_scanner()
        client = MagicMock()
        row = _make_intent_row(max_entry_price=None)
        result = await scanner._check_price(client, "SOL", row)
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_passes_when_below_max(self):
        scanner = _make_scanner()
        client = MagicMock()
        client.get_all_mids = AsyncMock(return_value={"SOL": 90.0})

        row = _make_intent_row(max_entry_price=100.0)
        result = await scanner._check_price(client, "SOL", row)
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_fails_when_above_max(self):
        scanner = _make_scanner()
        client = MagicMock()
        client.get_all_mids = AsyncMock(return_value={"SOL": 110.0})

        row = _make_intent_row(max_entry_price=100.0)
        result = await scanner._check_price(client, "SOL", row)
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# Expiry Tests
# ---------------------------------------------------------------------------


class TestIntentExpiry:
    """Tests for intent expiry."""

    @pytest.mark.asyncio
    async def test_expire_updates_status(self):
        db = _make_mock_db()
        scanner = _make_scanner(db=db)

        await scanner._expire_intent("intent_1")

        db.execute.assert_called_once()
        assert "status = 'expired'" in db.execute.call_args.args[0]

    @pytest.mark.asyncio
    async def test_fail_updates_status_with_error(self):
        db = _make_mock_db()
        scanner = _make_scanner(db=db)

        await scanner._fail_intent("intent_1", "Something went wrong")

        db.execute.assert_called_once()
        assert "status = 'failed'" in db.execute.call_args.args[0]
        assert db.execute.call_args.args[1][0] == "Something went wrong"


# ---------------------------------------------------------------------------
# Execute Intent Tests
# ---------------------------------------------------------------------------


class TestExecuteIntent:
    """Tests for intent execution."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        db = _make_mock_db()
        scanner = _make_scanner(db=db)

        row = _make_intent_row()
        criteria = {"all_passed": True, "checks": {}}

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_pm = MagicMock()
        mock_pm.__aenter__ = AsyncMock(return_value=mock_pm)
        mock_pm.__aexit__ = AsyncMock(return_value=None)
        mock_pm.open_position = AsyncMock(return_value={
            "success": True,
            "position_id": "pos_123",
            "asgard_pda": "pda_123",
        })

        with patch("bot.core.intent_scanner.UserTradingContext") as mock_utc:
            mock_utc.from_user_id = AsyncMock(return_value=mock_ctx)
            with patch("bot.core.intent_scanner.PositionManager") as mock_pm_cls:
                mock_pm_cls.from_user_context.return_value = mock_pm

                await scanner._execute_intent(row, criteria)

        # Should have inserted position + updated intent (via transaction)
        tx = db._mock_tx
        executed_calls = [c for c in tx.execute.call_args_list if "executed" in str(c)]
        assert len(executed_calls) > 0

    @pytest.mark.asyncio
    async def test_failed_execution_marks_intent_failed(self):
        db = _make_mock_db()
        scanner = _make_scanner(db=db)

        row = _make_intent_row()
        criteria = {"all_passed": True}

        with patch("bot.core.intent_scanner.UserTradingContext") as mock_utc:
            mock_utc.from_user_id = AsyncMock(side_effect=ValueError("No wallets"))

            with patch.object(scanner, "_fail_intent", new_callable=AsyncMock) as mock_fail:
                await scanner._execute_intent(row, criteria)
                mock_fail.assert_called_once()
                assert "No wallets" in mock_fail.call_args.args[1]


# ---------------------------------------------------------------------------
# Utility Tests
# ---------------------------------------------------------------------------


class TestParseDateTime:
    """Tests for datetime parsing utility."""

    def test_parses_iso_format(self):
        result = _parse_datetime("2026-01-15T12:30:00")
        assert result is not None
        assert result.year == 2026

    def test_returns_none_for_none(self):
        assert _parse_datetime(None) is None

    def test_returns_none_for_invalid(self):
        assert _parse_datetime("not-a-date") is None

    def test_passes_through_datetime(self):
        dt = datetime(2026, 1, 1)
        assert _parse_datetime(dt) is dt
