"""Tests for funding API — deposit capping (N12) and withdrawal balance check (N9)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.dashboard.api.funding import (
    MAX_AUTO_BRIDGE_USDC,
    deposit_to_hl,
    withdraw_from_hl,
    DepositRequest,
    WithdrawRequest,
)


def _make_user(user_id="did:privy:test123"):
    user = MagicMock()
    user.user_id = user_id
    return user


def _make_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(return_value=[])
    return db


def _make_redis(locked=False):
    redis = MagicMock()
    redis.set = AsyncMock(return_value=not locked)
    redis.delete = AsyncMock()
    return redis


# ---------------------------------------------------------------------------
# 5.1a: Auto-bridge amount capping (N12)
# ---------------------------------------------------------------------------


class TestDepositCapping:

    @pytest.mark.asyncio
    @patch("backend.dashboard.api.funding.get_redis")
    async def test_deposit_over_cap_rejected(self, mock_get_redis):
        """Deposits exceeding MAX_AUTO_BRIDGE_USDC are rejected."""
        from fastapi import HTTPException

        request = DepositRequest(amount_usdc=MAX_AUTO_BRIDGE_USDC + 1)
        user = _make_user()
        db = _make_db()

        with pytest.raises(HTTPException) as exc_info:
            await deposit_to_hl(request, user, db)

        assert exc_info.value.status_code == 400
        assert "Maximum bridge deposit" in exc_info.value.detail
        assert "Split into multiple deposits" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("backend.dashboard.api.funding.get_redis")
    async def test_deposit_at_cap_accepted(self, mock_get_redis):
        """Deposits exactly at the cap are accepted (job created)."""
        mock_get_redis.return_value = _make_redis(locked=False)

        request = DepositRequest(amount_usdc=MAX_AUTO_BRIDGE_USDC)
        user = _make_user()
        db = _make_db()

        # Patch asyncio.create_task so we don't actually run the job
        with patch("backend.dashboard.api.funding.asyncio.create_task"):
            response = await deposit_to_hl(request, user, db)

        assert response.status == "pending"
        assert response.job_id is not None

    @pytest.mark.asyncio
    @patch("backend.dashboard.api.funding.get_redis")
    async def test_deposit_below_cap_accepted(self, mock_get_redis):
        """Normal deposits are accepted."""
        mock_get_redis.return_value = _make_redis(locked=False)

        request = DepositRequest(amount_usdc=100.0)
        user = _make_user()
        db = _make_db()

        with patch("backend.dashboard.api.funding.asyncio.create_task"):
            response = await deposit_to_hl(request, user, db)

        assert response.status == "pending"

    def test_max_auto_bridge_default(self):
        """Default cap is $25,000."""
        assert MAX_AUTO_BRIDGE_USDC == 25000.0


# ---------------------------------------------------------------------------
# 5.2a: Withdrawal available balance check (N9)
# ---------------------------------------------------------------------------


class TestWithdrawalBalanceCheck:

    @pytest.mark.asyncio
    @patch("backend.dashboard.api.funding.get_redis")
    async def test_withdraw_exceeding_available_rejected(self, mock_get_redis):
        """Withdrawal exceeding withdrawable balance returns error with available amount."""
        from fastapi import HTTPException

        request = WithdrawRequest(amount_usdc=5000.0)
        user = _make_user()
        db = _make_db()

        # Mock the UserTradingContext to return a trader with limited withdrawable
        mock_trader = MagicMock()
        mock_trader.get_withdrawable_balance = AsyncMock(return_value=2000.0)

        mock_ctx = MagicMock()
        mock_ctx.get_hl_trader.return_value = mock_trader
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "bot.venues.user_context.UserTradingContext"
        ) as mock_utc_cls:
            mock_utc_cls.from_user_id = AsyncMock(return_value=mock_ctx)

            with pytest.raises(HTTPException) as exc_info:
                await withdraw_from_hl(request, user, db)

        assert exc_info.value.status_code == 400
        assert "$2,000.00" in exc_info.value.detail
        assert "margin for open positions" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("backend.dashboard.api.funding.get_redis")
    async def test_withdraw_within_available_accepted(self, mock_get_redis):
        """Withdrawal within available balance is accepted."""
        mock_get_redis.return_value = _make_redis(locked=False)

        request = WithdrawRequest(amount_usdc=1000.0)
        user = _make_user()
        db = _make_db()

        mock_trader = MagicMock()
        mock_trader.get_withdrawable_balance = AsyncMock(return_value=5000.0)

        mock_ctx = MagicMock()
        mock_ctx.get_hl_trader.return_value = mock_trader
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "bot.venues.user_context.UserTradingContext"
        ) as mock_utc_cls:
            mock_utc_cls.from_user_id = AsyncMock(return_value=mock_ctx)

            with patch("backend.dashboard.api.funding.asyncio.create_task"):
                response = await withdraw_from_hl(request, user, db)

        assert response.status == "pending"
        assert response.job_id is not None

    @pytest.mark.asyncio
    @patch("backend.dashboard.api.funding.get_redis")
    async def test_withdraw_exact_available_accepted(self, mock_get_redis):
        """Withdrawal of exactly the available amount is accepted."""
        mock_get_redis.return_value = _make_redis(locked=False)

        request = WithdrawRequest(amount_usdc=3000.0)
        user = _make_user()
        db = _make_db()

        mock_trader = MagicMock()
        mock_trader.get_withdrawable_balance = AsyncMock(return_value=3000.0)

        mock_ctx = MagicMock()
        mock_ctx.get_hl_trader.return_value = mock_trader
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "bot.venues.user_context.UserTradingContext"
        ) as mock_utc_cls:
            mock_utc_cls.from_user_id = AsyncMock(return_value=mock_ctx)

            with patch("backend.dashboard.api.funding.asyncio.create_task"):
                response = await withdraw_from_hl(request, user, db)

        assert response.status == "pending"
