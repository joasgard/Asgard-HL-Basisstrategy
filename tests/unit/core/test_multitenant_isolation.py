"""Tests for multi-tenant isolation (6.8).

Verifies that per-user state is properly isolated:
- Risk engine proximity tracking doesn't leak between users
- Per-user pause works independently
- Internal API returns only the requesting user's data
- One user's error doesn't affect another in scan/monitor loops
"""
import pytest
import time
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi.security import HTTPAuthorizationCredentials


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_A = "did:privy:user_a"
USER_B = "did:privy:user_b"


def _make_asgard_position(pda: str, health_factor: Decimal = Decimal("0.50")):
    """Build a minimal AsgardPosition mock."""
    pos = MagicMock()
    pos.position_pda = pda
    pos.health_factor = health_factor
    return pos


def _make_hl_position(position_id: str, margin_fraction: Decimal = Decimal("0.50")):
    """Build a minimal HyperliquidPosition mock."""
    pos = MagicMock()
    pos.position_id = position_id
    pos.margin_fraction = margin_fraction
    return pos


def _make_combined_position(
    position_id: str,
    user_id: str,
    pda: str = "pda1",
    health_factor: Decimal = Decimal("0.50"),
    margin_fraction: Decimal = Decimal("0.50"),
):
    """Build a minimal CombinedPosition mock with user_id."""
    pos = MagicMock()
    pos.position_id = position_id
    pos.user_id = user_id
    pos.status = "open"
    pos.asgard = _make_asgard_position(pda, health_factor)
    pos.asgard.asset = MagicMock(value="SOL")
    pos.asgard.leverage = Decimal("3.0")
    pos.asgard.collateral_usd = Decimal("10000")
    pos.asgard.current_value_usd = Decimal("30000")
    pos.asgard.current_health_factor = Decimal("1.2")
    pos.hyperliquid = MagicMock()
    pos.hyperliquid.size_usd = Decimal("30000")
    pos.hyperliquid.margin_fraction = margin_fraction
    pos.delta = Decimal("0")
    pos.delta_ratio = Decimal("0")
    pos.total_pnl = Decimal("0")
    pos.net_funding_pnl = Decimal("0")
    pos.created_at = datetime.utcnow()
    return pos


# ---------------------------------------------------------------------------
# Risk Engine: proximity state isolation
# ---------------------------------------------------------------------------

class TestRiskEngineIsolation:
    """Proximity tracking must be namespaced per user."""

    def test_proximity_keys_namespaced_by_user(self):
        """Two users at the same position PDA get separate proximity keys."""
        from bot.core.risk_engine import RiskEngine

        engine = RiskEngine()

        pos_a = _make_asgard_position("pda_shared", Decimal("0.22"))
        pos_b = _make_asgard_position("pda_shared", Decimal("0.80"))

        # User A near threshold → starts proximity tracking
        result_a = engine.check_asgard_health(pos_a, user_id=USER_A)
        assert f"{USER_A}:asgard_pda_shared" in engine._proximity_start_times

        # User B safe → should NOT have proximity tracking
        result_b = engine.check_asgard_health(pos_b, user_id=USER_B)
        assert f"{USER_B}:asgard_pda_shared" not in engine._proximity_start_times

        # User A's entry still present
        assert f"{USER_A}:asgard_pda_shared" in engine._proximity_start_times

    def test_proximity_does_not_leak_between_users(self):
        """Clearing one user's proximity doesn't affect the other."""
        from bot.core.risk_engine import RiskEngine

        engine = RiskEngine()

        # Both users in proximity
        pos_near = _make_asgard_position("pda_x", Decimal("0.22"))
        engine.check_asgard_health(pos_near, user_id=USER_A)
        engine.check_asgard_health(pos_near, user_id=USER_B)

        assert f"{USER_A}:asgard_pda_x" in engine._proximity_start_times
        assert f"{USER_B}:asgard_pda_x" in engine._proximity_start_times

        # User A moves to safety → clears only A's key
        pos_safe = _make_asgard_position("pda_x", Decimal("0.80"))
        engine.check_asgard_health(pos_safe, user_id=USER_A)

        assert f"{USER_A}:asgard_pda_x" not in engine._proximity_start_times
        assert f"{USER_B}:asgard_pda_x" in engine._proximity_start_times

    def test_hl_margin_proximity_namespaced(self):
        """Hyperliquid margin proximity keys are also user-namespaced."""
        from bot.core.risk_engine import RiskEngine

        engine = RiskEngine()

        pos_near = _make_hl_position("hl_1", Decimal("0.11"))
        pos_safe = _make_hl_position("hl_1", Decimal("0.50"))

        engine.check_hyperliquid_margin(pos_near, user_id=USER_A)
        engine.check_hyperliquid_margin(pos_safe, user_id=USER_B)

        assert f"{USER_A}:hyperliquid_hl_1" in engine._proximity_start_times
        assert f"{USER_B}:hyperliquid_hl_1" not in engine._proximity_start_times


# ---------------------------------------------------------------------------
# Per-user pause controller
# ---------------------------------------------------------------------------

class TestPerUserPause:
    """Per-user pause should be independent of global and other users."""

    @pytest.mark.asyncio
    async def test_pause_user_a_does_not_affect_user_b(self):
        """Pausing user A leaves user B unpaused."""
        from bot.core.pause_controller import PauseController

        controller = PauseController(admin_api_key="key")

        db = AsyncMock()
        # pause user A
        await controller.pause_user(USER_A, "testing", db)
        db.execute.assert_called_once()

        # check user B → not paused (DB returns no paused_at)
        db.fetchone = AsyncMock(return_value={"paused_at": None})
        result = await controller.check_user_paused(USER_B, db)
        assert result is False

    @pytest.mark.asyncio
    async def test_global_pause_overrides_per_user(self):
        """Global pause means ALL users are paused, regardless of DB state."""
        from bot.core.pause_controller import PauseController

        controller = PauseController(admin_api_key="key")
        controller.pause("key", "global maintenance")

        db = AsyncMock()
        # DB says user is NOT individually paused, but global pause is on
        db.fetchone = AsyncMock(return_value={"paused_at": None})

        result = await controller.check_user_paused(USER_A, db)
        assert result is True

    @pytest.mark.asyncio
    async def test_per_user_pause_with_global_resume(self):
        """User is paused in DB but global is not → user is paused."""
        from bot.core.pause_controller import PauseController

        controller = PauseController(admin_api_key="key")
        # global NOT paused

        db = AsyncMock()
        db.fetchone = AsyncMock(return_value={"paused_at": datetime.utcnow()})

        result = await controller.check_user_paused(USER_A, db)
        assert result is True

    @pytest.mark.asyncio
    async def test_resume_user_clears_pause(self):
        """Resuming a user clears paused_at in DB."""
        from bot.core.pause_controller import PauseController

        controller = PauseController(admin_api_key="key")

        db = AsyncMock()
        await controller.resume_user(USER_A, db)
        db.execute.assert_called_once()
        # Verify the SQL sets paused_at = NULL
        call_args = db.execute.call_args
        assert "NULL" in call_args[0][0]


# ---------------------------------------------------------------------------
# Internal API: user scoping via JWT
# ---------------------------------------------------------------------------

class TestInternalAPIUserScoping:
    """Positions endpoint must return only the authenticated user's data."""

    @pytest.mark.asyncio
    async def test_jwt_user_sees_only_own_positions(self):
        """GET /internal/positions with JWT returns only the JWT user's positions."""
        from bot.core.internal_api import get_positions, set_bot_instance

        pos_a = _make_combined_position("pos_a", USER_A, pda="pda_a")
        pos_b = _make_combined_position("pos_b", USER_B, pda="pda_b")

        mock_bot = MagicMock()
        mock_bot.get_positions.return_value = {"pos_a": pos_a, "pos_b": pos_b}
        set_bot_instance(mock_bot)

        try:
            with patch(
                "bot.core.internal_api.verify_internal_token", return_value=USER_A
            ):
                creds = HTTPAuthorizationCredentials(
                    scheme="Bearer", credentials="jwt_token"
                )
                result = await get_positions(creds)

            assert "pos_a" in result
            assert "pos_b" not in result
        finally:
            set_bot_instance(None)

    @pytest.mark.asyncio
    async def test_jwt_user_cannot_access_other_users_position_detail(self):
        """GET /internal/positions/{id} returns 404 for another user's position."""
        from bot.core.internal_api import get_position_detail, set_bot_instance
        from fastapi import HTTPException

        pos_b = _make_combined_position("pos_b", USER_B, pda="pda_b")
        pos_b.is_at_risk = False
        pos_b.asgard.position_size_usd = Decimal("30000")
        pos_b.asgard.token_b_borrowed = Decimal("20000")
        pos_b.asgard.pnl_usd = Decimal("0")
        pos_b.asgard.position_pda = "pda_b"
        pos_b.asgard.token_a_amount = Decimal("100")
        pos_b.asgard.entry_price_token_a = Decimal("150")
        pos_b.asgard.current_token_a_price = Decimal("155")
        pos_b.asgard.current_health_factor = Decimal("1.2")
        pos_b.hyperliquid.unrealized_pnl = Decimal("0")
        pos_b.hyperliquid.size_sol = Decimal("100")
        pos_b.hyperliquid.entry_px = Decimal("150")
        pos_b.hyperliquid.mark_px = Decimal("155")
        pos_b.hyperliquid.leverage = Decimal("3")
        pos_b.hyperliquid.margin_used = Decimal("5000")

        mock_bot = MagicMock()
        mock_bot.get_positions.return_value = {"pos_b": pos_b}
        set_bot_instance(mock_bot)

        try:
            with patch(
                "bot.core.internal_api.verify_internal_token", return_value=USER_A
            ):
                creds = HTTPAuthorizationCredentials(
                    scheme="Bearer", credentials="jwt_token"
                )
                with pytest.raises(HTTPException) as exc_info:
                    await get_position_detail("pos_b", creds)
                # 404 not 403 to prevent enumeration
                assert exc_info.value.status_code == 404
        finally:
            set_bot_instance(None)

    @pytest.mark.asyncio
    async def test_legacy_token_sees_all_positions(self):
        """Legacy (raw token) auth returns ALL positions (no user scoping)."""
        from bot.core.internal_api import get_positions, set_bot_instance

        pos_a = _make_combined_position("pos_a", USER_A, pda="pda_a")
        pos_b = _make_combined_position("pos_b", USER_B, pda="pda_b")

        mock_bot = MagicMock()
        mock_bot.get_positions.return_value = {"pos_a": pos_a, "pos_b": pos_b}
        set_bot_instance(mock_bot)

        try:
            # Legacy token returns "" (empty string) → no user scoping
            with patch(
                "bot.core.internal_api.verify_internal_token", return_value=""
            ):
                creds = HTTPAuthorizationCredentials(
                    scheme="Bearer", credentials="raw_token"
                )
                result = await get_positions(creds)

            assert "pos_a" in result
            assert "pos_b" in result
        finally:
            set_bot_instance(None)

    @pytest.mark.asyncio
    async def test_jwt_with_user_id_generates_correctly(self):
        """generate_internal_jwt embeds user_id in sub claim."""
        from shared.auth.internal_jwt import generate_internal_jwt, verify_internal_jwt

        secret = "test-secret-multitenant"
        token = generate_internal_jwt(USER_A, secret)
        recovered = verify_internal_jwt(token, secret)
        assert recovered == USER_A

        # Different user gets different token content
        token_b = generate_internal_jwt(USER_B, secret)
        recovered_b = verify_internal_jwt(token_b, secret)
        assert recovered_b == USER_B
        assert recovered_b != recovered


# ---------------------------------------------------------------------------
# Error boundaries: one user's failure doesn't crash others
# ---------------------------------------------------------------------------

class TestErrorBoundaries:
    """Intent scanner and position monitor wrap per-user work in try/except."""

    @pytest.mark.asyncio
    async def test_intent_scanner_error_in_one_intent_continues_others(self):
        """IntentScanner processes remaining intents even if one fails."""
        from bot.core.intent_scanner import IntentScanner

        db = AsyncMock()
        # Two intents: first will raise, second should still be processed
        db.fetchall = AsyncMock(return_value=[
            {"id": "i1", "user_id": USER_A, "status": "active",
             "expires_at": None, "data": "{}"},
            {"id": "i2", "user_id": USER_B, "status": "active",
             "expires_at": None, "data": "{}"},
        ])

        scanner = IntentScanner(db=db)

        call_count = 0

        async def mock_process(row, now):
            nonlocal call_count
            call_count += 1
            if row["id"] == "i1":
                raise RuntimeError("Simulated failure for user A")
            # For i2 just return (success)

        scanner._process_intent = mock_process

        # Should not raise — error is caught per-intent
        await scanner._scan_cycle()

        assert call_count == 2, "Both intents should be attempted"

    @pytest.mark.asyncio
    async def test_position_monitor_error_in_one_user_continues_others(self):
        """PositionMonitorService processes remaining users if one fails."""
        from bot.core.position_monitor import PositionMonitorService

        db = AsyncMock()
        risk_engine = MagicMock()

        # Two users' positions
        db.fetchall = AsyncMock(return_value=[
            {"id": "p1", "user_id": USER_A, "status": "open",
             "data": '{"position_id": "p1"}', "updated_at": datetime.utcnow()},
            {"id": "p2", "user_id": USER_B, "status": "open",
             "data": '{"position_id": "p2"}', "updated_at": datetime.utcnow()},
        ])

        monitor = PositionMonitorService(db=db, risk_engine=risk_engine)

        users_attempted = []

        async def mock_monitor_user(user_id, positions):
            users_attempted.append(user_id)
            if user_id == USER_A:
                raise RuntimeError("Simulated failure for user A")

        monitor._monitor_user_positions = mock_monitor_user

        # Should not raise
        await monitor._monitor_cycle()

        assert USER_A in users_attempted
        assert USER_B in users_attempted
        assert len(users_attempted) == 2
