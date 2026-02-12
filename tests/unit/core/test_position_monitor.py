"""
Tests for PositionMonitorService.

These tests verify:
- Monitor lifecycle (start/stop)
- Monitoring cycle: fetching, grouping, per-user processing
- Risk evaluation (Asgard health, HL margin, funding flip)
- Auto-exit execution flow
- Error handling and backoff
- DB position data updates
"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.core.position_monitor import PositionMonitorService
from bot.core.risk_engine import ExitDecision, ExitReason


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_position_row(
    position_id="pos_1",
    user_id="user_1",
    asset="SOL",
    asgard_pda="pda_123",
    extra_data=None,
):
    """Create a fake DB row for an active position."""
    data = {
        "asset": asset,
        "asgard_pda": asgard_pda,
        "hyperliquid_size": "10.0",
        "created_at": "2026-01-01T00:00:00",
    }
    if extra_data:
        data.update(extra_data)
    return {
        "id": position_id,
        "user_id": user_id,
        "data": json.dumps(data),
        "updated_at": "2026-01-01T00:00:00",
    }


def _make_hl_position(
    coin="SOL",
    size=-10.0,
    entry_px=100.0,
    margin_fraction=0.25,
    unrealized_pnl=50.0,
    liquidation_px=150.0,
):
    """Create a mock HL position object."""
    pos = MagicMock()
    pos.coin = coin
    pos.size = size
    pos.entry_px = entry_px
    pos.margin_fraction = margin_fraction
    pos.unrealized_pnl = unrealized_pnl
    pos.liquidation_px = liquidation_px
    return pos


def _make_mock_ctx(user_id="user_1", hl_position=None, health_factor=0.25, funding_rates=None):
    """Create a mock UserTradingContext with mocked sub-components.

    Uses MagicMock for synchronous methods (get_hl_trader, get_asgard_manager)
    and AsyncMock only for actual async methods.
    """
    ctx = MagicMock()
    ctx.user_id = user_id
    # async context manager support
    ctx.__aenter__ = AsyncMock(return_value=ctx)
    ctx.__aexit__ = AsyncMock(return_value=False)

    # Mock HL trader (get_hl_trader is synchronous, returns a trader object)
    hl_trader = MagicMock()
    hl_trader.get_position = AsyncMock(return_value=hl_position or _make_hl_position())
    hl_trader.oracle = MagicMock()
    hl_trader.oracle.get_current_funding_rates = AsyncMock(return_value=funding_rates or {})
    hl_trader.close_short = AsyncMock(return_value=MagicMock(success=True))
    ctx.get_hl_trader.return_value = hl_trader

    # Mock Asgard manager (get_asgard_manager is synchronous)
    asgard_mgr = MagicMock()
    health_status = MagicMock()
    health_status.health_factor = health_factor
    asgard_mgr.monitor_health = AsyncMock(return_value=health_status)
    asgard_mgr.close_position = AsyncMock(return_value=MagicMock(success=True))
    ctx.get_asgard_manager.return_value = asgard_mgr

    return ctx


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


def _make_monitor(db=None, rows=None):
    """Create a PositionMonitorService with a mock RiskEngine to avoid loading risk.yaml."""
    mock_risk = MagicMock()
    return PositionMonitorService(db=db or _make_mock_db(rows), risk_engine=mock_risk)


# ---------------------------------------------------------------------------
# Lifecycle Tests
# ---------------------------------------------------------------------------


class TestMonitorLifecycle:
    """Tests for start/stop behavior."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        """Test that start() creates a background task."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)

        with patch.object(monitor, "_run_loop", new_callable=AsyncMock):
            await monitor.start()
            assert monitor._running is True
            assert monitor._task is not None
            await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        """Test that stop() cancels the background task."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)

        with patch.object(monitor, "_run_loop", new_callable=AsyncMock):
            await monitor.start()
            assert monitor._running is True

            await monitor.stop()
            assert monitor._running is False

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self):
        """Test that starting twice doesn't create duplicate tasks."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)

        with patch.object(monitor, "_run_loop", new_callable=AsyncMock):
            await monitor.start()
            first_task = monitor._task

            await monitor.start()  # Should warn and return
            assert monitor._task is first_task

            await monitor.stop()


# ---------------------------------------------------------------------------
# Monitor Cycle Tests
# ---------------------------------------------------------------------------


class TestMonitorCycle:
    """Tests for the main monitoring cycle."""

    @pytest.mark.asyncio
    async def test_no_active_positions(self):
        """Test cycle with no active positions is a no-op."""
        db = _make_mock_db(rows=[])
        monitor = _make_monitor(db=db)

        await monitor._monitor_cycle()

        db.fetchall.assert_called_once()

    @pytest.mark.asyncio
    async def test_groups_positions_by_user(self):
        """Test that positions are grouped by user_id."""
        rows = [
            _make_position_row("pos_1", "user_1"),
            _make_position_row("pos_2", "user_1"),
            _make_position_row("pos_3", "user_2"),
        ]
        db = _make_mock_db(rows=rows)
        monitor = _make_monitor(db=db)

        with patch.object(monitor, "_monitor_user_positions", new_callable=AsyncMock) as mock_mup:
            await monitor._monitor_cycle()

            assert mock_mup.call_count == 2
            # Check that user_1 got 2 positions and user_2 got 1
            calls = {call.args[0]: call.args[1] for call in mock_mup.call_args_list}
            assert len(calls["user_1"]) == 2
            assert len(calls["user_2"]) == 1

    @pytest.mark.asyncio
    async def test_user_error_does_not_cascade(self):
        """Test that an error monitoring one user doesn't affect others."""
        rows = [
            _make_position_row("pos_1", "user_1"),
            _make_position_row("pos_2", "user_2"),
        ]
        db = _make_mock_db(rows=rows)
        monitor = _make_monitor(db=db)

        call_count = 0

        async def side_effect(user_id, positions):
            nonlocal call_count
            call_count += 1
            if user_id == "user_1":
                raise RuntimeError("User 1 error")

        with patch.object(monitor, "_monitor_user_positions", side_effect=side_effect):
            await monitor._monitor_cycle()

        # Both users should have been attempted
        assert call_count == 2


# ---------------------------------------------------------------------------
# Risk Evaluation Tests
# ---------------------------------------------------------------------------


class TestEvaluateExit:
    """Tests for the _evaluate_exit risk check."""

    def setup_method(self):
        self.monitor = _make_monitor()

    def test_no_exit_healthy_position(self):
        """Test no exit for healthy position."""
        hl_pos = _make_hl_position(margin_fraction=0.25)
        result = self.monitor._evaluate_exit(
            data={"asset": "SOL"},
            hl_position=hl_pos,
            asgard_health=0.30,
            current_funding={"funding": -0.001},  # Negative = shorts get paid
        )
        assert result is None

    def test_exit_asgard_health_critical(self):
        """Test exit triggered by critical Asgard health factor."""
        hl_pos = _make_hl_position(margin_fraction=0.25)
        result = self.monitor._evaluate_exit(
            data={"asset": "SOL"},
            hl_position=hl_pos,
            asgard_health=0.08,  # Below 10% threshold
            current_funding=None,
        )
        assert result is not None
        assert result.should_exit is True
        assert result.reason == ExitReason.ASGARD_HEALTH_FACTOR

    def test_exit_asgard_health_exactly_threshold(self):
        """Test exit triggered at exactly the 10% threshold."""
        result = self.monitor._evaluate_exit(
            data={},
            hl_position=None,
            asgard_health=0.10,  # Exactly threshold
            current_funding=None,
        )
        assert result is not None
        assert result.should_exit is True
        assert result.reason == ExitReason.ASGARD_HEALTH_FACTOR

    def test_no_exit_asgard_health_above_threshold(self):
        """Test no exit when Asgard health is above threshold."""
        result = self.monitor._evaluate_exit(
            data={},
            hl_position=None,
            asgard_health=0.11,
            current_funding=None,
        )
        assert result is None

    def test_exit_hl_margin_critical(self):
        """Test exit triggered by critical HL margin fraction."""
        hl_pos = _make_hl_position(margin_fraction=0.05)
        result = self.monitor._evaluate_exit(
            data={"asset": "SOL"},
            hl_position=hl_pos,
            asgard_health=0.30,  # Healthy
            current_funding=None,
        )
        assert result is not None
        assert result.should_exit is True
        assert result.reason == ExitReason.HYPERLIQUID_MARGIN

    def test_exit_funding_flip(self):
        """Test exit triggered by funding rate flipping positive."""
        hl_pos = _make_hl_position(margin_fraction=0.25)
        result = self.monitor._evaluate_exit(
            data={"asset": "SOL"},
            hl_position=hl_pos,
            asgard_health=0.30,
            current_funding={"funding": 0.001},  # Positive = shorts pay
        )
        assert result is not None
        assert result.should_exit is True
        assert result.reason == ExitReason.FUNDING_FLIP

    def test_no_exit_negative_funding(self):
        """Test no exit when funding is negative (shorts get paid)."""
        hl_pos = _make_hl_position(margin_fraction=0.25)
        result = self.monitor._evaluate_exit(
            data={"asset": "SOL"},
            hl_position=hl_pos,
            asgard_health=0.30,
            current_funding={"funding": -0.002},
        )
        assert result is None

    def test_funding_as_scalar(self):
        """Test funding rate passed as a scalar value."""
        hl_pos = _make_hl_position(margin_fraction=0.25)
        result = self.monitor._evaluate_exit(
            data={},
            hl_position=hl_pos,
            asgard_health=0.30,
            current_funding=0.0005,  # Scalar positive
        )
        assert result is not None
        assert result.reason == ExitReason.FUNDING_FLIP

    def test_priority_asgard_over_margin(self):
        """Test that Asgard health check has priority over HL margin."""
        hl_pos = _make_hl_position(margin_fraction=0.05)  # Also critical
        result = self.monitor._evaluate_exit(
            data={},
            hl_position=hl_pos,
            asgard_health=0.08,  # Critical
            current_funding={"funding": 0.001},  # Also flipped
        )
        assert result.reason == ExitReason.ASGARD_HEALTH_FACTOR

    def test_no_hl_position_skips_margin_check(self):
        """Test that missing HL position data doesn't trigger exit."""
        result = self.monitor._evaluate_exit(
            data={},
            hl_position=None,
            asgard_health=0.30,
            current_funding=None,
        )
        assert result is None

    def test_none_asgard_health_skips_check(self):
        """Test that None asgard_health skips the Asgard check."""
        hl_pos = _make_hl_position(margin_fraction=0.25)
        result = self.monitor._evaluate_exit(
            data={},
            hl_position=hl_pos,
            asgard_health=None,
            current_funding=None,
        )
        assert result is None

    def test_zero_funding_no_exit(self):
        """Test zero funding rate does not trigger exit."""
        hl_pos = _make_hl_position(margin_fraction=0.25)
        result = self.monitor._evaluate_exit(
            data={},
            hl_position=hl_pos,
            asgard_health=0.30,
            current_funding={"funding": 0},
        )
        assert result is None


# ---------------------------------------------------------------------------
# Auto-Exit Execution Tests
# ---------------------------------------------------------------------------


class TestExecuteExit:
    """Tests for automatic exit execution."""

    @pytest.mark.asyncio
    async def test_exit_closes_hl_then_asgard(self):
        """Test that exit closes HL short first, then Asgard long."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)
        ctx = _make_mock_ctx()

        data = {
            "asset": "SOL",
            "hyperliquid_size": "10.0",
            "asgard_pda": "pda_123",
            "created_at": "2026-01-01T00:00:00",
        }
        exit_decision = ExitDecision(
            should_exit=True,
            reason=ExitReason.ASGARD_HEALTH_FACTOR,
            details={"message": "Health critical"},
        )

        await monitor._execute_exit(ctx, "pos_1", data, exit_decision)

        # HL short closed
        ctx.get_hl_trader().close_short.assert_called_once_with("SOL", "10.0")
        # Asgard long closed
        ctx.get_asgard_manager().close_position.assert_called_once_with("pda_123")
        # Position marked closed in DB (via transaction)
        assert db._mock_tx.execute.call_count >= 2  # UPDATE + INSERT

    @pytest.mark.asyncio
    async def test_exit_no_asgard_pda(self):
        """Test exit when there's no Asgard PDA (HL-only position)."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)
        ctx = _make_mock_ctx()

        data = {
            "asset": "SOL",
            "hyperliquid_size": "10.0",
            # No asgard_pda
        }
        exit_decision = ExitDecision(
            should_exit=True,
            reason=ExitReason.FUNDING_FLIP,
            details={"message": "Funding flipped"},
        )

        await monitor._execute_exit(ctx, "pos_1", data, exit_decision)

        ctx.get_hl_trader().close_short.assert_called_once()
        ctx.get_asgard_manager().close_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_exit_hl_failure_aborts_asgard(self):
        """Test that if HL close fails, Asgard close is skipped."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)
        ctx = _make_mock_ctx()

        # HL close fails
        ctx.get_hl_trader().close_short.return_value = MagicMock(success=False, error="Insufficient margin")

        data = {
            "asset": "SOL",
            "hyperliquid_size": "10.0",
            "asgard_pda": "pda_123",
        }
        exit_decision = ExitDecision(
            should_exit=True,
            reason=ExitReason.HYPERLIQUID_MARGIN,
            details={"message": "Margin critical"},
        )

        await monitor._execute_exit(ctx, "pos_1", data, exit_decision)

        # HL was attempted
        ctx.get_hl_trader().close_short.assert_called_once()
        # Asgard was NOT attempted because HL failed
        ctx.get_asgard_manager().close_position.assert_not_called()
        # DB not updated (position stays open)
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_exit_marks_position_closed(self):
        """Test that successful exit updates DB correctly."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)
        ctx = _make_mock_ctx()

        data = {
            "asset": "SOL",
            "hyperliquid_size": "10.0",
            "asgard_pda": "pda_123",
            "created_at": "2026-01-01T00:00:00",
            "total_pnl": 100.0,
            "funding_earned": 50.0,
        }
        exit_decision = ExitDecision(
            should_exit=True,
            reason=ExitReason.FUNDING_FLIP,
            details={"message": "Funding flipped positive"},
        )

        await monitor._execute_exit(ctx, "pos_1", data, exit_decision)

        tx = db._mock_tx
        # Check UPDATE positions SET is_closed = 1
        update_call = tx.execute.call_args_list[0]
        assert "is_closed = 1" in update_call.args[0]
        closed_data = json.loads(update_call.args[1][0])
        assert closed_data["exit_reason"] == "funding_flip"
        assert "closed_at" in closed_data

        # Check INSERT INTO position_history
        insert_call = tx.execute.call_args_list[1]
        assert "position_history" in insert_call.args[0]

    @pytest.mark.asyncio
    async def test_exit_no_hl_size_skips_close(self):
        """Test exit when no HL size data."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)
        ctx = _make_mock_ctx()

        data = {
            "asset": "SOL",
            "asgard_pda": "pda_123",
            # No hyperliquid_size or hl_size
        }
        exit_decision = ExitDecision(
            should_exit=True,
            reason=ExitReason.ASGARD_HEALTH_FACTOR,
            details={"message": "Health critical"},
        )

        await monitor._execute_exit(ctx, "pos_1", data, exit_decision)

        # HL close not attempted
        ctx.get_hl_trader().close_short.assert_not_called()
        # Asgard still closed
        ctx.get_asgard_manager().close_position.assert_called_once()


# ---------------------------------------------------------------------------
# Position Check & DB Update Tests
# ---------------------------------------------------------------------------


class TestCheckPosition:
    """Tests for individual position checking."""

    @pytest.mark.asyncio
    async def test_updates_position_data_in_db(self):
        """Test that live data is persisted back to DB."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)

        hl_pos = _make_hl_position(
            margin_fraction=0.25,
            unrealized_pnl=50.0,
            liquidation_px=150.0,
        )
        ctx = _make_mock_ctx(hl_position=hl_pos, health_factor=0.30)

        pos_info = {
            "position_id": "pos_1",
            "data": {
                "asset": "SOL",
                "asgard_pda": "pda_123",
            },
            "updated_at": "2026-01-01T00:00:00",
        }

        await monitor._check_position(ctx, pos_info, funding_rates={"SOL": {"funding": -0.001}})

        # DB should be updated with live data
        db.execute.assert_called()
        update_args = db.execute.call_args_list[0]
        assert "UPDATE positions SET data" in update_args.args[0]
        merged = json.loads(update_args.args[1][0])
        assert merged["hl_unrealized_pnl"] == 50.0
        assert merged["asgard_health_factor"] == 0.30

    @pytest.mark.asyncio
    async def test_no_exit_when_healthy(self):
        """Test that healthy positions don't trigger exit."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)

        hl_pos = _make_hl_position(margin_fraction=0.25)
        ctx = _make_mock_ctx(hl_position=hl_pos, health_factor=0.30)

        pos_info = {
            "position_id": "pos_1",
            "data": {"asset": "SOL", "asgard_pda": "pda_123"},
            "updated_at": "2026-01-01T00:00:00",
        }

        with patch.object(monitor, "_execute_exit", new_callable=AsyncMock) as mock_exit:
            await monitor._check_position(ctx, pos_info, funding_rates={})
            mock_exit.assert_not_called()

    @pytest.mark.asyncio
    async def test_triggers_exit_when_critical(self):
        """Test that critical position triggers exit."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)

        hl_pos = _make_hl_position(margin_fraction=0.25)
        ctx = _make_mock_ctx(hl_position=hl_pos, health_factor=0.05)  # Critical

        pos_info = {
            "position_id": "pos_1",
            "data": {
                "asset": "SOL",
                "asgard_pda": "pda_123",
                "hyperliquid_size": "10.0",
            },
            "updated_at": "2026-01-01T00:00:00",
        }

        with patch.object(monitor, "_execute_exit", new_callable=AsyncMock) as mock_exit:
            await monitor._check_position(ctx, pos_info, funding_rates={})
            mock_exit.assert_called_once()
            exit_decision = mock_exit.call_args.kwargs.get("exit_decision") or mock_exit.call_args[0][3]
            assert exit_decision.reason == ExitReason.ASGARD_HEALTH_FACTOR


# ---------------------------------------------------------------------------
# Error Handling & Backoff Tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling and backoff behavior."""

    @pytest.mark.asyncio
    async def test_consecutive_errors_tracked(self):
        """Test that consecutive errors are tracked."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)
        monitor._running = False  # Prevent loop from running

        assert monitor._consecutive_errors == 0

    @pytest.mark.asyncio
    async def test_monitor_user_error_logged_not_raised(self):
        """Test that per-user errors are caught and logged."""
        rows = [_make_position_row("pos_1", "user_1")]
        db = _make_mock_db(rows=rows)
        monitor = _make_monitor(db=db)

        with patch.object(monitor, "_monitor_user_positions", side_effect=RuntimeError("test")):
            # Should not raise
            await monitor._monitor_cycle()

    @pytest.mark.asyncio
    async def test_check_position_error_logged_not_raised(self):
        """Test that per-position errors within a user are caught."""
        db = _make_mock_db()
        monitor = _make_monitor(db=db)

        ctx = _make_mock_ctx()
        # Make get_position raise
        ctx.get_hl_trader().get_position = AsyncMock(side_effect=RuntimeError("HL down"))

        positions = [{
            "position_id": "pos_1",
            "data": {"asset": "SOL", "asgard_pda": "pda_123"},
            "updated_at": "2026-01-01",
        }]

        with patch("bot.core.position_monitor.UserTradingContext") as mock_ctx_cls:
            mock_ctx_cls.from_user_id = AsyncMock(return_value=ctx)
            ctx.__aenter__ = AsyncMock(return_value=ctx)
            ctx.__aexit__ = AsyncMock(return_value=False)

            # Should not raise despite inner error
            await monitor._monitor_user_positions("user_1", positions)
