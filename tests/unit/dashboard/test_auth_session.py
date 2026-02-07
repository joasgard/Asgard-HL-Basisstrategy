"""
Tests for dashboard authentication and session management.
"""
import pytest
import secrets
import hmac
import hashlib
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi import HTTPException, Request, Response
from fastapi.testclient import TestClient

from src.dashboard.auth import (
    Session, SessionManager, SessionError, InvalidSessionError, CSRFError,
    PrivyAuth, User, session_manager, set_session_cookie, set_csrf_cookie,
    clear_session_cookies, SESSION_COOKIE_NAME, CSRF_COOKIE_NAME,
    get_current_session, require_csrf, get_current_user, require_role,
    verify_api_key, security
)


class TestSession:
    """Tests for Session dataclass."""
    
    def test_session_creation(self):
        """Test creating a session."""
        now = datetime.utcnow()
        session = Session(
            id="test_session_id",
            privy_user_id="user123",
            email="test@example.com",
            created_at=now,
            expires_at=now + timedelta(hours=8),
            last_activity=now,
            csrf_token="csrf_token_123",
            ip_address="127.0.0.1",
            user_agent="TestBrowser/1.0"
        )
        
        assert session.id == "test_session_id"
        assert session.privy_user_id == "user123"
        assert session.email == "test@example.com"
        assert session.csrf_token == "csrf_token_123"
    
    def test_session_is_expired_true(self):
        """Test is_expired when session has expired."""
        now = datetime.utcnow()
        session = Session(
            id="test_id",
            privy_user_id="user123",
            email=None,
            created_at=now - timedelta(hours=10),
            expires_at=now - timedelta(hours=2),  # Expired 2 hours ago
            last_activity=now - timedelta(hours=3),
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        
        assert session.is_expired is True
    
    def test_session_is_expired_false(self):
        """Test is_expired when session is still valid."""
        now = datetime.utcnow()
        session = Session(
            id="test_id",
            privy_user_id="user123",
            email=None,
            created_at=now,
            expires_at=now + timedelta(hours=8),
            last_activity=now,
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        
        assert session.is_expired is False
    
    def test_session_is_inactive_true(self):
        """Test is_inactive when session timed out."""
        now = datetime.utcnow()
        session = Session(
            id="test_id",
            privy_user_id="user123",
            email=None,
            created_at=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=7),
            last_activity=now - timedelta(minutes=35),  # 35 minutes ago
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        
        assert session.is_inactive is True
    
    def test_session_is_inactive_false(self):
        """Test is_inactive when session is active."""
        now = datetime.utcnow()
        session = Session(
            id="test_id",
            privy_user_id="user123",
            email=None,
            created_at=now,
            expires_at=now + timedelta(hours=8),
            last_activity=now - timedelta(minutes=10),  # 10 minutes ago
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        
        assert session.is_inactive is False
    
    def test_session_touch(self):
        """Test touch updates last_activity."""
        now = datetime.utcnow()
        session = Session(
            id="test_id",
            privy_user_id="user123",
            email=None,
            created_at=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=7),
            last_activity=now - timedelta(minutes=30),
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        
        old_activity = session.last_activity
        session.touch()
        
        assert session.last_activity > old_activity


class TestSessionError:
    """Tests for SessionError exceptions."""
    
    def test_session_error_creation(self):
        """Test creating SessionError."""
        error = SessionError("Test error")
        assert str(error) == "Test error"
    
    def test_invalid_session_error_creation(self):
        """Test creating InvalidSessionError."""
        error = InvalidSessionError("Session expired")
        assert str(error) == "Session expired"
        assert isinstance(error, SessionError)
    
    def test_csrf_error_creation(self):
        """Test creating CSRFError."""
        error = CSRFError("Invalid CSRF")
        assert str(error) == "Invalid CSRF"
        assert isinstance(error, SessionError)


class TestSessionManager:
    """Tests for SessionManager."""
    
    def test_session_manager_initialization(self):
        """Test SessionManager initialization."""
        sm = SessionManager()
        assert sm._sessions == {}
        assert sm._db is None
    
    def test_set_db(self):
        """Test setting database connection."""
        sm = SessionManager()
        mock_db = MagicMock()
        
        sm.set_db(mock_db)
        
        assert sm._db is mock_db
    
    def test_derive_kek(self):
        """Test KEK derivation."""
        sm = SessionManager()
        
        kek1 = sm._derive_kek("user123", "secret456")
        kek2 = sm._derive_kek("user123", "secret456")
        kek3 = sm._derive_kek("user789", "secret456")
        
        # Same inputs should produce same KEK
        assert kek1 == kek2
        # Different user should produce different KEK
        assert kek1 != kek3
        # Should be bytes
        assert isinstance(kek1, bytes)
        # Should be 32 bytes (SHA256)
        assert len(kek1) == 32
    
    @pytest.mark.asyncio
    @patch('src.dashboard.auth.EncryptionManager.unlock_with_dek')
    async def test_create_session(self, mock_unlock):
        """Test creating a new session."""
        sm = SessionManager()
        
        with patch.object(sm, '_derive_kek', return_value=b'kek_bytes' * 4):  # 32 bytes
            with patch.object(sm, '_get_or_create_dek', return_value=b'encrypted_dek'):
                session = await sm.create_session(
                    privy_user_id="user123",
                    email="test@example.com",
                    ip_address="127.0.0.1",
                    user_agent="TestBrowser",
                    server_secret="server_secret"
                )
        
        assert session.privy_user_id == "user123"
        assert session.email == "test@example.com"
        assert session.ip_address == "127.0.0.1"
        assert session.user_agent == "TestBrowser"
        assert len(session.id) > 20  # session_id should be long
        assert len(session.csrf_token) > 20
        assert session.id in sm._sessions
        mock_unlock.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_session_valid(self):
        """Test getting a valid session."""
        sm = SessionManager()
        now = datetime.utcnow()
        
        session = Session(
            id="session123",
            privy_user_id="user123",
            email=None,
            created_at=now,
            expires_at=now + timedelta(hours=8),
            last_activity=now,
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        sm._sessions["session123"] = session
        
        result = await sm.get_session("session123")
        
        assert result is session
    
    @pytest.mark.asyncio
    async def test_get_session_not_found(self):
        """Test getting non-existent session."""
        sm = SessionManager()
        
        result = await sm.get_session("nonexistent")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_session_expired(self):
        """Test getting expired session raises error."""
        sm = SessionManager()
        now = datetime.utcnow()
        
        session = Session(
            id="session123",
            privy_user_id="user123",
            email=None,
            created_at=now - timedelta(hours=10),
            expires_at=now - timedelta(hours=2),
            last_activity=now - timedelta(hours=3),
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        sm._sessions["session123"] = session
        
        with pytest.raises(InvalidSessionError):
            await sm.get_session("session123")
        
        # Session should be removed
        assert "session123" not in sm._sessions
    
    @pytest.mark.asyncio
    async def test_get_session_inactive(self):
        """Test getting inactive session raises error."""
        sm = SessionManager()
        now = datetime.utcnow()
        
        session = Session(
            id="session123",
            privy_user_id="user123",
            email=None,
            created_at=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=7),
            last_activity=now - timedelta(minutes=35),
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        sm._sessions["session123"] = session
        
        with pytest.raises(InvalidSessionError):
            await sm.get_session("session123")
        
        # Session should be removed
        assert "session123" not in sm._sessions
    
    @pytest.mark.asyncio
    async def test_validate_csrf_valid(self):
        """Test CSRF validation with valid token."""
        sm = SessionManager()
        now = datetime.utcnow()
        
        session = Session(
            id="session123",
            privy_user_id="user123",
            email=None,
            created_at=now,
            expires_at=now + timedelta(hours=8),
            last_activity=now,
            csrf_token="valid_csrf_token",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        sm._sessions["session123"] = session
        
        result = await sm.validate_csrf("session123", "valid_csrf_token")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_csrf_invalid(self):
        """Test CSRF validation with invalid token."""
        sm = SessionManager()
        now = datetime.utcnow()
        
        session = Session(
            id="session123",
            privy_user_id="user123",
            email=None,
            created_at=now,
            expires_at=now + timedelta(hours=8),
            last_activity=now,
            csrf_token="valid_csrf_token",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        sm._sessions["session123"] = session
        
        result = await sm.validate_csrf("session123", "wrong_token")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_csrf_session_not_found(self):
        """Test CSRF validation when session not found."""
        sm = SessionManager()
        
        result = await sm.validate_csrf("nonexistent", "token")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_touch_session(self):
        """Test touching a session updates activity."""
        sm = SessionManager()
        now = datetime.utcnow()
        
        session = Session(
            id="session123",
            privy_user_id="user123",
            email=None,
            created_at=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=7),
            last_activity=now - timedelta(minutes=20),
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        sm._sessions["session123"] = session
        
        old_activity = session.last_activity
        await sm.touch_session("session123")
        
        assert session.last_activity > old_activity
    
    @pytest.mark.asyncio
    async def test_touch_session_not_found(self):
        """Test touching non-existent session."""
        sm = SessionManager()
        
        # Should not raise
        await sm.touch_session("nonexistent")
    
    @pytest.mark.asyncio
    async def test_destroy_session(self):
        """Test destroying a session."""
        sm = SessionManager()
        now = datetime.utcnow()
        
        session = Session(
            id="session123",
            privy_user_id="user123",
            email=None,
            created_at=now,
            expires_at=now + timedelta(hours=8),
            last_activity=now,
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        sm._sessions["session123"] = session
        
        await sm.destroy_session("session123")
        
        assert "session123" not in sm._sessions
        assert not session.encryption_manager.is_unlocked
    
    @pytest.mark.asyncio
    async def test_cleanup_expired(self):
        """Test cleaning up expired sessions."""
        sm = SessionManager()
        now = datetime.utcnow()
        
        # Expired session
        expired_session = Session(
            id="expired",
            privy_user_id="user1",
            email=None,
            created_at=now - timedelta(hours=10),
            expires_at=now - timedelta(hours=2),
            last_activity=now - timedelta(hours=3),
            csrf_token="csrf1",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        sm._sessions["expired"] = expired_session
        
        # Active session
        active_session = Session(
            id="active",
            privy_user_id="user2",
            email=None,
            created_at=now,
            expires_at=now + timedelta(hours=8),
            last_activity=now,
            csrf_token="csrf2",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        sm._sessions["active"] = active_session
        
        count = await sm.cleanup_expired()
        
        assert count == 1
        assert "expired" not in sm._sessions
        assert "active" in sm._sessions


class TestCookieHelpers:
    """Tests for cookie helper functions."""
    
    def test_set_session_cookie(self):
        """Test setting session cookie."""
        response = MagicMock(spec=Response)
        
        set_session_cookie(response, "session_id_123")
        
        response.set_cookie.assert_called_once()
        call_args = response.set_cookie.call_args
        assert call_args[1]["key"] == SESSION_COOKIE_NAME
        assert call_args[1]["value"] == "session_id_123"
        assert call_args[1]["httponly"] is True
        assert call_args[1]["secure"] is True
        assert call_args[1]["samesite"] == "strict"
    
    def test_set_csrf_cookie(self):
        """Test setting CSRF cookie."""
        response = MagicMock(spec=Response)
        
        set_csrf_cookie(response, "csrf_token_123")
        
        response.set_cookie.assert_called_once()
        call_args = response.set_cookie.call_args
        assert call_args[1]["key"] == CSRF_COOKIE_NAME
        assert call_args[1]["value"] == "csrf_token_123"
        assert call_args[1]["httponly"] is False  # JS needs to read this
        assert call_args[1]["secure"] is True
    
    def test_clear_session_cookies(self):
        """Test clearing session cookies."""
        response = MagicMock(spec=Response)
        
        clear_session_cookies(response)
        
        assert response.delete_cookie.call_count == 2
        calls = response.delete_cookie.call_args_list
        # Check positional args or keyword args
        first_call = calls[0]
        if first_call[0]:
            assert first_call[0][0] == SESSION_COOKIE_NAME or first_call[1].get("path") == "/"
        else:
            assert first_call[1].get("path") == "/"


class TestUser:
    """Tests for User model."""
    
    def test_user_creation(self):
        """Test creating a User."""
        user = User(user_id="user123", email="test@example.com", role="admin")
        
        assert user.user_id == "user123"
        assert user.email == "test@example.com"
        assert user.role == "admin"
    
    def test_user_default_role(self):
        """Test User default role."""
        user = User(user_id="user123")
        
        assert user.role == "admin"
        assert user.email is None


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""
    
    @pytest.mark.asyncio
    async def test_get_current_user(self):
        """Test getting current user from session."""
        now = datetime.utcnow()
        session = Session(
            id="session123",
            privy_user_id="user123",
            email="test@example.com",
            created_at=now,
            expires_at=now + timedelta(hours=8),
            last_activity=now,
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        
        user = await get_current_user(session)
        
        assert user.user_id == "user123"
        assert user.email == "test@example.com"
        assert user.role == "admin"


class TestRequireRole:
    """Tests for require_role dependency factory."""
    
    @pytest.mark.asyncio
    async def test_require_admin_success(self):
        """Test require_admin with admin role."""
        now = datetime.utcnow()
        session = Session(
            id="session123",
            privy_user_id="user123",
            email=None,
            created_at=now,
            expires_at=now + timedelta(hours=8),
            last_activity=now,
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        
        checker = require_role(["admin"])
        user = await checker(session)
        
        assert user.user_id == "user123"
        assert user.role == "admin"
    
    @pytest.mark.asyncio
    async def test_require_admin_forbidden(self):
        """Test require_role without admin."""
        now = datetime.utcnow()
        session = Session(
            id="session123",
            privy_user_id="user123",
            email=None,
            created_at=now,
            expires_at=now + timedelta(hours=8),
            last_activity=now,
            csrf_token="csrf123",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        
        checker = require_role(["operator"])  # No admin in roles
        
        with pytest.raises(HTTPException) as exc_info:
            await checker(session)
        
        assert exc_info.value.status_code == 403
    
    def test_predefined_role_dependencies(self):
        """Test predefined role dependencies exist."""
        from src.dashboard.auth import require_admin, require_operator, require_viewer
        
        assert callable(require_admin)
        assert callable(require_operator)
        assert callable(require_viewer)


class TestVerifyApiKey:
    """Tests for verify_api_key function."""
    
    def test_verify_api_key_valid(self):
        """Test verifying valid API key."""
        with patch('src.dashboard.auth.get_dashboard_settings') as mock_settings:
            mock_settings.return_value = MagicMock(bot_admin_key="correct_key")
            
            result = verify_api_key("correct_key")
            
            assert result is True
    
    def test_verify_api_key_invalid(self):
        """Test verifying invalid API key."""
        with patch('src.dashboard.auth.get_dashboard_settings') as mock_settings:
            mock_settings.return_value = MagicMock(bot_admin_key="correct_key")
            
            result = verify_api_key("wrong_key")
            
            assert result is False
