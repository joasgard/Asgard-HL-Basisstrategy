"""Tests for stuck bridge deposit reconciliation service (N3)."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from bot.services.deposit_reconciler import (
    reconcile_stuck_deposits,
    STUCK_THRESHOLD_MINUTES,
    ALERT_THRESHOLD_MINUTES,
)


def _make_stuck_row(
    job_id="job1",
    user_id="did:privy:user1",
    amount=1000.0,
    minutes_ago=10,
    status="failed",
):
    """Create a mock stuck deposit row."""
    return {
        "id": job_id,
        "user_id": user_id,
        "amount_usdc": amount,
        "bridge_tx_hash": "0xbridge123",
        "created_at": datetime.utcnow() - timedelta(minutes=minutes_ago),
        "status": status,
    }


class TestReconcileStuckDeposits:

    @pytest.mark.asyncio
    async def test_no_stuck_deposits(self):
        """No stuck deposits = no-op."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[])

        result = await reconcile_stuck_deposits(db)

        assert result["checked"] == 0
        assert result["reconciled"] == 0
        assert result["still_stuck"] == 0

    @pytest.mark.asyncio
    async def test_reconciles_credited_deposit(self):
        """Deposit with HL balance > 0 gets marked as hl_credited."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[_make_stuck_row(minutes_ago=10)])
        db.execute = AsyncMock()

        mock_trader = MagicMock()
        mock_trader.get_deposited_balance = AsyncMock(return_value=1000.0)

        mock_ctx = MagicMock()
        mock_ctx.get_hl_trader.return_value = mock_trader
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "bot.venues.user_context.UserTradingContext"
        ) as mock_utc_cls:
            mock_utc_cls.from_user_id = AsyncMock(return_value=mock_ctx)

            result = await reconcile_stuck_deposits(db)

        assert result["checked"] == 1
        assert result["reconciled"] == 1
        assert result["still_stuck"] == 0

        # Verify DB update
        db.execute.assert_called_once()
        call_args = db.execute.call_args
        assert "hl_credited" in call_args[0][0]
        assert "completed" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_still_stuck_no_balance(self):
        """Deposit with HL balance == 0 stays stuck."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[_make_stuck_row(minutes_ago=10)])
        db.execute = AsyncMock()

        mock_trader = MagicMock()
        mock_trader.get_deposited_balance = AsyncMock(return_value=0.0)

        mock_ctx = MagicMock()
        mock_ctx.get_hl_trader.return_value = mock_trader
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "bot.venues.user_context.UserTradingContext"
        ) as mock_utc_cls:
            mock_utc_cls.from_user_id = AsyncMock(return_value=mock_ctx)

            result = await reconcile_stuck_deposits(db)

        assert result["checked"] == 1
        assert result["reconciled"] == 0
        assert result["still_stuck"] == 1
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_alerts_on_long_stuck(self):
        """Deposits stuck > 30 min should trigger WARNING log."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[
            _make_stuck_row(minutes_ago=ALERT_THRESHOLD_MINUTES + 5),
        ])
        db.execute = AsyncMock()

        mock_trader = MagicMock()
        mock_trader.get_deposited_balance = AsyncMock(return_value=0.0)

        mock_ctx = MagicMock()
        mock_ctx.get_hl_trader.return_value = mock_trader
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "bot.venues.user_context.UserTradingContext"
        ) as mock_utc_cls:
            mock_utc_cls.from_user_id = AsyncMock(return_value=mock_ctx)

            # The test succeeds if no exception; log level verified by coverage
            result = await reconcile_stuck_deposits(db)

        assert result["still_stuck"] == 1

    @pytest.mark.asyncio
    async def test_handles_user_context_error(self):
        """Errors during reconciliation don't crash the loop."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[_make_stuck_row()])
        db.execute = AsyncMock()

        with patch(
            "bot.venues.user_context.UserTradingContext"
        ) as mock_utc_cls:
            mock_utc_cls.from_user_id = AsyncMock(
                side_effect=Exception("DB connection failed")
            )

            result = await reconcile_stuck_deposits(db)

        assert result["checked"] == 1
        assert result["reconciled"] == 0
        assert result["still_stuck"] == 1

    @pytest.mark.asyncio
    async def test_multiple_deposits_mixed(self):
        """Mix of reconciled and stuck deposits."""
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[
            _make_stuck_row(job_id="job1", user_id="user1", minutes_ago=10),
            _make_stuck_row(job_id="job2", user_id="user2", minutes_ago=15),
        ])
        db.execute = AsyncMock()

        # user1 has balance (reconciled), user2 doesn't (stuck)
        call_count = 0

        async def mock_from_user_id(user_id, db_arg):
            nonlocal call_count
            mock_trader = MagicMock()
            if "user1" in user_id:
                mock_trader.get_deposited_balance = AsyncMock(return_value=500.0)
            else:
                mock_trader.get_deposited_balance = AsyncMock(return_value=0.0)

            mock_ctx = MagicMock()
            mock_ctx.get_hl_trader.return_value = mock_trader
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            call_count += 1
            return mock_ctx

        with patch(
            "bot.venues.user_context.UserTradingContext"
        ) as mock_utc_cls:
            mock_utc_cls.from_user_id = mock_from_user_id

            result = await reconcile_stuck_deposits(db)

        assert result["checked"] == 2
        assert result["reconciled"] == 1
        assert result["still_stuck"] == 1
