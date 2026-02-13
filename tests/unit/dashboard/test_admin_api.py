"""Tests for admin API endpoints (7.4.3)."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path


class TestKillSwitchStatus:
    def test_inactive(self):
        from backend.dashboard.api.admin import get_kill_switch_status

        with patch.object(Path, 'exists', return_value=False):
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(
                get_kill_switch_status()
            )
        assert result.active is False

    def test_active(self):
        from backend.dashboard.api.admin import get_kill_switch_status

        with patch.object(Path, 'exists', return_value=True):
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(
                get_kill_switch_status()
            )
        assert result.active is True


class TestKillSwitchActivate:
    @pytest.mark.asyncio
    async def test_rejects_bad_key(self):
        from backend.dashboard.api.admin import _verify_admin_key
        from fastapi import HTTPException

        with patch.dict('os.environ', {'ADMIN_API_KEY': 'correct_key'}):
            with pytest.raises(HTTPException) as exc:
                _verify_admin_key("wrong_key")
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_accepts_correct_key(self):
        from backend.dashboard.api.admin import _verify_admin_key

        with patch.dict('os.environ', {'ADMIN_API_KEY': 'correct_key'}):
            result = _verify_admin_key("correct_key")
            assert result == "correct_key"

    @pytest.mark.asyncio
    async def test_rejects_no_key_configured(self):
        from backend.dashboard.api.admin import _verify_admin_key
        from fastapi import HTTPException

        with patch.dict('os.environ', {'ADMIN_API_KEY': ''}, clear=False):
            with patch('pathlib.Path.read_text', side_effect=FileNotFoundError):
                with pytest.raises(HTTPException) as exc:
                    _verify_admin_key("any_key")
                assert exc.value.status_code == 503


class TestCloseAllEndpoint:
    @pytest.mark.asyncio
    async def test_no_positions_returns_success(self):
        """close-all with no open positions still succeeds."""
        from backend.dashboard.api.positions import close_all_positions

        mock_db = AsyncMock()
        mock_db.fetchall = AsyncMock(return_value=[])
        mock_db.execute = AsyncMock()
        mock_user = MagicMock()
        mock_user.user_id = "did:privy:test"

        with patch('backend.dashboard.api.positions.get_db', return_value=mock_db):
            result = await close_all_positions(user=mock_user, db=mock_db)

        assert result.success is True
        assert result.positions_closed == 0
        # Should still pause strategy
        assert mock_db.execute.called
