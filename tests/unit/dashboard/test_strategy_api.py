"""Tests for per-user strategy configuration API (7.1.2)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.dashboard.api.strategy import (
    get_strategy,
    update_strategy,
    pause_strategy,
    resume_strategy,
    StrategyConfigUpdate,
)
from shared.config.strategy_defaults import DEFAULTS

USER_ID = "did:privy:test_user"


def _make_user():
    user = MagicMock()
    user.user_id = USER_ID
    return user


def _make_db_row(**overrides):
    """Return a dict that looks like a user_strategy_config DB row."""
    row = {
        "user_id": USER_ID,
        "enabled": False,
        "assets": ["SOL"],
        "protocols": None,
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
        "version": 1,
    }
    row.update(overrides)
    return row


class TestGetStrategy:
    """GET /strategy tests."""

    @pytest.mark.asyncio
    async def test_returns_defaults_when_no_row(self):
        db = AsyncMock()
        db.fetchone = AsyncMock(return_value=None)

        result = await get_strategy(user=_make_user(), db=db)

        assert result.is_default is True
        assert result.version == 1
        assert result.min_carry_apy == DEFAULTS.min_carry_apy
        assert result.cooldown_minutes == DEFAULTS.cooldown_minutes

    @pytest.mark.asyncio
    async def test_returns_saved_config(self):
        db = AsyncMock()
        db.fetchone = AsyncMock(return_value=_make_db_row(
            enabled=True, max_leverage=2.5, version=3
        ))

        result = await get_strategy(user=_make_user(), db=db)

        assert result.is_default is False
        assert result.enabled is True
        assert result.max_leverage == 2.5
        assert result.version == 3


class TestUpdateStrategy:
    """PUT /strategy tests."""

    @pytest.mark.asyncio
    async def test_first_save_inserts_row(self):
        db = AsyncMock()
        # No existing row
        db.fetchone = AsyncMock(side_effect=[
            None,  # first call: check existence
            _make_db_row(enabled=True, version=1),  # second: re-read after insert
        ])
        db.execute = AsyncMock()

        body = StrategyConfigUpdate(enabled=True, version=1)
        result = await update_strategy(body=body, user=_make_user(), db=db)

        db.execute.assert_called_once()
        assert "INSERT" in db.execute.call_args[0][0]

    @pytest.mark.asyncio
    async def test_update_with_matching_version(self):
        db = AsyncMock()
        db.fetchone = AsyncMock(side_effect=[
            {"version": 2},  # existing row
            _make_db_row(max_leverage=2.0, version=3),  # after update
        ])
        db.execute = AsyncMock()

        body = StrategyConfigUpdate(max_leverage=2.0, version=2)
        result = await update_strategy(body=body, user=_make_user(), db=db)

        db.execute.assert_called_once()
        assert "UPDATE" in db.execute.call_args[0][0]

    @pytest.mark.asyncio
    async def test_version_conflict_raises_409(self):
        db = AsyncMock()
        db.fetchone = AsyncMock(return_value={"version": 3})

        body = StrategyConfigUpdate(max_leverage=2.0, version=1)  # stale

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await update_strategy(body=body, user=_make_user(), db=db)

        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_empty_update_raises_400(self):
        db = AsyncMock()

        body = StrategyConfigUpdate(version=1)  # no actual updates

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await update_strategy(body=body, user=_make_user(), db=db)

        assert exc.value.status_code == 400


class TestValidation:
    """Pydantic validation on StrategyConfigUpdate."""

    def test_rejects_unknown_assets(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StrategyConfigUpdate(assets=["BTC"], version=1)

    def test_rejects_leverage_above_system_max(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StrategyConfigUpdate(max_leverage=10.0, version=1)

    def test_rejects_cooldown_below_system_min(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StrategyConfigUpdate(cooldown_minutes=1, version=1)

    def test_rejects_stop_loss_below_system_min(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StrategyConfigUpdate(stop_loss_pct=0.5, version=1)

    def test_accepts_valid_config(self):
        body = StrategyConfigUpdate(
            max_leverage=2.5,
            stop_loss_pct=5.0,
            cooldown_minutes=10,
            version=1,
        )
        assert body.max_leverage == 2.5


class TestPauseResume:
    """POST /strategy/pause and /strategy/resume."""

    @pytest.mark.asyncio
    async def test_pause_executes_upsert(self):
        db = AsyncMock()
        db.execute = AsyncMock()

        result = await pause_strategy(user=_make_user(), db=db)

        assert result["success"] is True
        sql = db.execute.call_args[0][0]
        assert "paused_at" in sql
        assert "ON CONFLICT" in sql

    @pytest.mark.asyncio
    async def test_resume_clears_pause(self):
        db = AsyncMock()
        db.execute = AsyncMock()

        result = await resume_strategy(user=_make_user(), db=db)

        assert result["success"] is True
        sql = db.execute.call_args[0][0]
        assert "enabled = TRUE" in sql
        assert "paused_at = NULL" in sql


class TestStrategyDefaults:
    """Tests for shared/config/strategy_defaults.py (7.1.4)."""

    def test_defaults_are_conservative(self):
        assert DEFAULTS.min_carry_apy == 15.0
        assert DEFAULTS.max_position_pct == 0.25
        assert DEFAULTS.max_leverage == 3.0
        assert DEFAULTS.stop_loss_pct == 10.0
        assert DEFAULTS.auto_reopen is True
        assert DEFAULTS.cooldown_minutes == 30

    def test_to_dict_round_trips(self):
        from shared.config.strategy_defaults import to_dict
        d = to_dict()
        assert d["min_carry_apy"] == 15.0
        assert d["cooldown_minutes"] == 30
        assert "version" not in d  # version is not a default

    def test_defaults_frozen(self):
        from dataclasses import FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            DEFAULTS.min_carry_apy = 99.0
