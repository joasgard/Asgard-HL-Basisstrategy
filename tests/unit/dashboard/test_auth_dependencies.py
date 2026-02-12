"""
Tests for dashboard authentication dependencies.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from backend.dashboard.auth import (
    Session, SessionManager, InvalidSessionError,
    SESSION_COOKIE_NAME, CSRF_COOKIE_NAME,
    get_current_session, require_csrf, get_encryption_manager,
    get_current_user, User
)


class TestGetCurrentSession:
    """Tests for get_current_session dependency."""
    
    @pytest.fixture
    def mock_request(self):
        """Create a mock request with cookies."""
        request = MagicMock(spec=Request)
        request.cookies = {}
        return request
    
    @pytest.fixture
    def valid_session(self):
        """Create a valid session."""
        now = datetime.utcnow()
        return Session(
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
    
    @pytest.mark.asyncio
    async def test_no_session_cookie(self, mock_request):
        """Test when no session cookie exists."""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_session(mock_request)
        
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_session_not_found(self, mock_request):
        """Test when session cookie exists but session not in memory."""
        mock_request.cookies[SESSION_COOKIE_NAME] = "invalid_session"
        
        with patch('backend.dashboard.auth.session_manager') as mock_sm:
            mock_sm.get_session = AsyncMock(return_value=None)
            
            with pytest.raises(HTTPException) as exc_info:
                await get_current_session(mock_request)
            
            assert exc_info.value.status_code == 401
            assert "Invalid session" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_session_expired(self, mock_request):
        """Test when session has expired."""
        mock_request.cookies[SESSION_COOKIE_NAME] = "expired_session"
        
        with patch('backend.dashboard.auth.session_manager') as mock_sm:
            mock_sm.get_session = AsyncMock(
                side_effect=InvalidSessionError("Session expired")
            )
            mock_sm.destroy_session = AsyncMock()
            
            with pytest.raises(HTTPException) as exc_info:
                await get_current_session(mock_request)
            
            assert exc_info.value.status_code == 401
            assert "Session expired" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_valid_session(self, mock_request, valid_session):
        """Test successful session retrieval."""
        mock_request.cookies[SESSION_COOKIE_NAME] = "session123"
        
        with patch('backend.dashboard.auth.session_manager') as mock_sm:
            mock_sm.get_session = AsyncMock(return_value=valid_session)
            mock_sm.touch_session = AsyncMock()
            
            session = await get_current_session(mock_request)
            
            assert session is valid_session
            mock_sm.touch_session.assert_called_once_with("session123")


class TestRequireCsrf:
    """Tests for require_csrf dependency."""
    
    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.cookies = {}
        request.headers = {}
        return request
    
    @pytest.mark.asyncio
    async def test_no_session_cookie(self, mock_request):
        """Test when no session cookie exists."""
        with pytest.raises(HTTPException) as exc_info:
            await require_csrf(mock_request)
        
        assert exc_info.value.status_code == 403
        assert "CSRF token required" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_no_csrf_header(self, mock_request):
        """Test when CSRF header is missing."""
        mock_request.cookies[SESSION_COOKIE_NAME] = "session123"
        
        with pytest.raises(HTTPException) as exc_info:
            await require_csrf(mock_request)
        
        assert exc_info.value.status_code == 403
        assert "CSRF token required" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_invalid_csrf(self, mock_request):
        """Test with invalid CSRF token."""
        mock_request.cookies[SESSION_COOKIE_NAME] = "session123"
        mock_request.headers["X-CSRF-Token"] = "wrong_token"
        
        with patch('backend.dashboard.auth.session_manager') as mock_sm:
            mock_sm.validate_csrf = AsyncMock(return_value=False)
            
            with pytest.raises(HTTPException) as exc_info:
                await require_csrf(mock_request)
            
            assert exc_info.value.status_code == 403
            assert "Invalid CSRF token" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_valid_csrf(self, mock_request):
        """Test with valid CSRF token."""
        mock_request.cookies[SESSION_COOKIE_NAME] = "session123"
        mock_request.headers["X-CSRF-Token"] = "valid_csrf_token"
        
        with patch('backend.dashboard.auth.session_manager') as mock_sm:
            mock_sm.validate_csrf = AsyncMock(return_value=True)
            
            # Should not raise
            await require_csrf(mock_request)
            
            mock_sm.validate_csrf.assert_called_once_with("session123", "valid_csrf_token")


class TestGetEncryptionManager:
    """Tests for get_encryption_manager dependency."""
    
    @pytest.mark.asyncio
    async def test_encryption_unlocked(self):
        """Test when encryption is unlocked."""
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
        
        # Unlock the encryption manager
        session.encryption_manager._dek = b'test_dek_32_bytes_long_______'
        
        em = await get_encryption_manager(session)
        assert em is session.encryption_manager
    
    @pytest.mark.asyncio
    async def test_encryption_locked(self):
        """Test when encryption is locked."""
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
        
        # Ensure encryption manager is locked
        session.encryption_manager._dek = None
        
        with pytest.raises(HTTPException) as exc_info:
            await get_encryption_manager(session)
        
        assert exc_info.value.status_code == 401
        assert "Encryption not unlocked" in exc_info.value.detail


class TestPrivyAuth:
    """Tests for PrivyAuth class using the official SDK."""
    
    def test_initialization(self):
        """Test PrivyAuth initialization stores credentials for lazy loading."""
        from backend.dashboard.auth import PrivyAuth
        
        auth = PrivyAuth("app_id", "app_secret")
        
        # New implementation uses lazy loading - credentials stored in _app_id/_app_secret
        assert auth._app_id == "app_id"
        assert auth._app_secret == "app_secret"
        # Client is lazy-loaded
        assert auth._client is None
    
    @pytest.mark.asyncio
    @patch('backend.dashboard.privy_client.PrivyClient')
    async def test_verify_token(self, mock_client_class):
        """Test token verification delegates to SDK client."""
        from backend.dashboard.auth import PrivyAuth
        
        mock_client = AsyncMock()
        mock_client.verify_access_token = AsyncMock(return_value={
            "id": "user_123",
            "email": "test@example.com",
            "wallet_address": "0x123"
        })
        mock_client_class.return_value = mock_client
        
        auth = PrivyAuth("app_id", "app_secret")
        result = await auth.verify_token("test_token")
        
        assert result["id"] == "user_123"
        assert result["email"] == "test@example.com"
        mock_client.verify_access_token.assert_called_once_with("test_token")
    
    @pytest.mark.asyncio
    @patch('backend.dashboard.privy_client.PrivyClient')
    async def test_get_user(self, mock_client_class):
        """Test get_user delegates to SDK client."""
        from backend.dashboard.auth import PrivyAuth
        
        mock_client = AsyncMock()
        mock_client.get_user = AsyncMock(return_value={
            "id": "user_123",
            "email": "test@example.com"
        })
        mock_client_class.return_value = mock_client
        
        auth = PrivyAuth("app_id", "app_secret")
        result = await auth.get_user("user_123")
        
        assert result["id"] == "user_123"
        mock_client.get_user.assert_called_once_with("user_123")
