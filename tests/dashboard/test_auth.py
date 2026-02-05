"""Tests for dashboard authentication module."""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from jose import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Import the module under test - do this BEFORE any mocking
import dashboard.auth as auth_module


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def clear_user_store():
    """Clear the user store cache before each test."""
    auth_module._user_store = None
    yield
    auth_module._user_store = None


@pytest.fixture
def mock_settings():
    """Provide mock dashboard settings."""
    with patch("dashboard.auth.get_dashboard_settings") as mock:
        mock.return_value = MagicMock(
            jwt_secret="test-jwt-secret-for-testing-only",
            bot_admin_key="test-api-key-12345"
        )
        yield mock


# =============================================================================
# Model Tests
# =============================================================================

class TestTokenData:
    """Tests for TokenData model."""

    def test_token_data_creation(self):
        """Test creating TokenData instance."""
        from dashboard.auth import TokenData
        
        token = TokenData(user_id="user123", role="admin", exp=datetime.utcnow())
        assert token.user_id == "user123"
        assert token.role == "admin"
        assert isinstance(token.exp, datetime)

    def test_token_data_validation(self):
        """Test TokenData validation."""
        from dashboard.auth import TokenData
        
        # Valid roles
        TokenData(user_id="u1", role="admin", exp=datetime.utcnow())
        TokenData(user_id="u2", role="operator", exp=datetime.utcnow())
        TokenData(user_id="u3", role="viewer", exp=datetime.utcnow())


class TestUser:
    """Tests for User model."""

    def test_user_creation(self):
        """Test creating User instance."""
        from dashboard.auth import User
        
        user = User(user_id="user123", role="admin")
        assert user.user_id == "user123"
        assert user.role == "admin"

    def test_user_roles(self):
        """Test User with different roles."""
        from dashboard.auth import User
        
        admin = User(user_id="a1", role="admin")
        assert admin.role == "admin"
        
        operator = User(user_id="o1", role="operator")
        assert operator.role == "operator"
        
        viewer = User(user_id="v1", role="viewer")
        assert viewer.role == "viewer"


# =============================================================================
# Password Hashing Tests
# =============================================================================

class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_get_password_hash(self):
        """Test generating password hash."""
        from dashboard.auth import get_password_hash
        
        password = "test_password"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        
        # Hashes should be different (salt)
        assert hash1 != hash2
        # Both should start with bcrypt marker
        assert hash1.startswith("$2")
        assert hash2.startswith("$2")

    def test_verify_password_correct(self):
        """Test verifying correct password."""
        from dashboard.auth import get_password_hash, verify_password
        
        password = "test_password"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test verifying incorrect password."""
        from dashboard.auth import get_password_hash, verify_password
        
        password = "test_password"
        wrong_password = "wrong_password"
        hashed = get_password_hash(password)
        
        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_different_hashes(self):
        """Test that different hashes work for same password."""
        from dashboard.auth import get_password_hash, verify_password
        
        password = "test_password"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        
        # Both hashes should verify the same password
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


# =============================================================================
# User Loading Tests
# =============================================================================

class TestLoadUsers:
    """Tests for _load_users function."""

    @patch.dict(os.environ, {"DASHBOARD_USERS": '{"admin": {"hash": "hashed_pass", "role": "admin"}}'})
    def test_load_users_from_env(self):
        """Test loading users from environment variable."""
        auth_module._user_store = None
        
        users = auth_module._load_users()
        
        assert "admin" in users
        assert users["admin"]["hash"] == "hashed_pass"
        assert users["admin"]["role"] == "admin"

    @patch.dict(os.environ, {"DASHBOARD_USERS": "invalid json"})
    def test_load_users_from_env_invalid_json(self):
        """Test loading users with invalid JSON in env var."""
        auth_module._user_store = None
        
        with pytest.raises(RuntimeError, match="invalid JSON"):
            auth_module._load_users()

    @patch.dict(os.environ, {}, clear=True)
    @patch("os.path.exists")
    @patch("builtins.open", mock_open(read_data='{"admin": {"hash": "hashed_pass", "role": "admin"}}'))
    def test_load_users_from_file(self, mock_exists):
        """Test loading users from file."""
        auth_module._user_store = None
        
        def exists_side_effect(path):
            return "dashboard_users.json" in str(path)
        mock_exists.side_effect = exists_side_effect
        
        users = auth_module._load_users()
        
        assert "admin" in users
        assert users["admin"]["hash"] == "hashed_pass"

    @patch.dict(os.environ, {}, clear=True)
    def test_load_users_from_file_not_found(self):
        """Test error when users file not found in production."""
        auth_module._user_store = None
        
        with pytest.raises(RuntimeError, match="No dashboard users configured"):
            auth_module._load_users()

    @patch.dict(os.environ, {}, clear=True)
    @patch("os.path.exists")
    @patch("builtins.open", mock_open(read_data="invalid json"))
    def test_load_users_from_file_invalid_json(self, mock_exists):
        """Test error when users file has invalid JSON."""
        auth_module._user_store = None
        
        def exists_side_effect(path):
            return "dashboard_users.json" in str(path)
        mock_exists.side_effect = exists_side_effect
        
        with pytest.raises(RuntimeError, match="Failed to load users"):
            auth_module._load_users()

    @patch.dict(os.environ, {"DASHBOARD_USERS": '{"admin": {"hash": "hash1", "role": "admin"}}'})
    def test_load_users_caching(self):
        """Test that users are cached after first load."""
        auth_module._user_store = None
        
        users1 = auth_module._load_users()
        
        # Modify the env var - shouldn't affect cached result
        with patch.dict(os.environ, {"DASHBOARD_USERS": '{"different": {"hash": "hash2", "role": "viewer"}}'}):
            users2 = auth_module._load_users()
        
        # Should return the same cached data
        assert users1 == users2
        assert "admin" in users2

    @patch.dict(os.environ, {}, clear=True)
    @patch.dict(os.environ, {"DASHBOARD_ENV": "development"})
    @patch("os.path.exists")
    @patch("builtins.open")
    def test_load_users_development_fallback_legacy_files(self, mock_open, mock_exists):
        """Test development fallback to legacy password files."""
        auth_module._user_store = None
        
        # First secrets dir doesn't exist, but legacy does
        def exists_side_effect(path):
            return "dashboard_admin_password.txt" in str(path) or "dashboard_viewer_password.txt" in str(path)
        mock_exists.side_effect = exists_side_effect
        
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=None)
        mock_file.read.return_value = "admin123"
        mock_open.return_value = mock_file
        
        with pytest.warns(RuntimeWarning):
            users = auth_module._load_users()
        
        assert "admin" in users or "viewer" in users  # At least one should exist

    @patch.dict(os.environ, {}, clear=True)
    @patch.dict(os.environ, {"DASHBOARD_ENV": "development"})
    def test_load_users_development_no_legacy_files(self):
        """Test development raises error when no files exist."""
        auth_module._user_store = None
        
        with pytest.warns(RuntimeWarning):
            with pytest.raises(RuntimeError, match="No dashboard users configured"):
                auth_module._load_users()


# =============================================================================
# JWT Token Tests
# =============================================================================

class TestCreateAccessToken:
    """Tests for create_access_token function."""

    def test_create_access_token_default_expiry(self, mock_settings):
        """Test creating token with default expiry."""
        from dashboard.auth import create_access_token
        
        token = create_access_token("user123", "admin")
        
        # Decode and verify
        payload = jwt.decode(token, "test-jwt-secret-for-testing-only", algorithms=["HS256"])
        assert payload["user_id"] == "user123"
        assert payload["role"] == "admin"
        assert "exp" in payload

    def test_create_access_token_custom_expiry(self, mock_settings):
        """Test creating token with custom expiry."""
        from dashboard.auth import create_access_token
        
        custom_expiry = timedelta(minutes=30)
        token = create_access_token("user123", "admin", expires_delta=custom_expiry)
        
        payload = jwt.decode(token, "test-jwt-secret-for-testing-only", algorithms=["HS256"])
        assert payload["user_id"] == "user123"
        assert payload["role"] == "admin"

    def test_create_access_token_different_users(self, mock_settings):
        """Test creating tokens for different users."""
        from dashboard.auth import create_access_token
        
        token1 = create_access_token("user1", "admin")
        token2 = create_access_token("user2", "viewer")
        
        payload1 = jwt.decode(token1, "test-jwt-secret-for-testing-only", algorithms=["HS256"])
        payload2 = jwt.decode(token2, "test-jwt-secret-for-testing-only", algorithms=["HS256"])
        
        assert payload1["user_id"] == "user1"
        assert payload1["role"] == "admin"
        assert payload2["user_id"] == "user2"
        assert payload2["role"] == "viewer"


class TestVerifyToken:
    """Tests for verify_token function."""

    def test_verify_token_valid(self, mock_settings):
        """Test verifying valid token."""
        from dashboard.auth import create_access_token, verify_token
        
        token = create_access_token("user123", "admin")
        token_data = verify_token(token)
        
        assert token_data.user_id == "user123"
        assert token_data.role == "admin"
        assert isinstance(token_data.exp, datetime)

    def test_verify_token_invalid_signature(self, mock_settings):
        """Test verifying token with wrong secret."""
        from dashboard.auth import create_access_token, verify_token
        
        # Create token with test secret
        token = create_access_token("user123", "admin")
        
        # Change settings to different secret
        with patch("dashboard.auth.get_dashboard_settings") as mock:
            mock.return_value = MagicMock(jwt_secret="different-secret")
            
            with pytest.raises(HTTPException) as exc_info:
                verify_token(token)
            
            assert exc_info.value.status_code == 401

    def test_verify_token_expired(self, mock_settings):
        """Test verifying expired token."""
        from dashboard.auth import create_access_token, verify_token
        
        # Create already-expired token
        expired_delta = timedelta(hours=-1)
        token = create_access_token("user123", "admin", expires_delta=expired_delta)
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401

    def test_verify_token_missing_user_id(self, mock_settings):
        """Test verifying token without user_id."""
        from dashboard.auth import verify_token
        
        # Create token without user_id
        payload_data = {"role": "admin", "exp": datetime.utcnow() + timedelta(hours=1)}
        token = jwt.encode(payload_data, "test-jwt-secret-for-testing-only", algorithm="HS256")
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401

    def test_verify_token_missing_role(self, mock_settings):
        """Test verifying token without role."""
        from dashboard.auth import verify_token
        
        # Create token without role
        payload_data = {"user_id": "user123", "exp": datetime.utcnow() + timedelta(hours=1)}
        token = jwt.encode(payload_data, "test-jwt-secret-for-testing-only", algorithm="HS256")
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401

    def test_verify_token_invalid_format(self, mock_settings):
        """Test verifying token with invalid format."""
        from dashboard.auth import verify_token
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token("not.a.valid.token")
        assert exc_info.value.status_code == 401


# =============================================================================
# Current User Tests
# =============================================================================

class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_settings):
        """Test getting current user with valid token."""
        from dashboard.auth import create_access_token, get_current_user
        
        token = create_access_token("user123", "admin")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        user = await get_current_user(credentials=credentials)
        
        assert user.user_id == "user123"
        assert user.role == "admin"

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_settings):
        """Test getting current user with invalid token."""
        from dashboard.auth import get_current_user
        
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.token.here")
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials)
        
        assert exc_info.value.status_code == 401


# =============================================================================
# Role Requirement Tests
# =============================================================================

class TestRequireRole:
    """Tests for require_role dependency."""

    def test_require_role_returns_callable(self):
        """Test that require_role returns a callable."""
        from dashboard.auth import require_role
        
        checker = require_role(["admin"])
        assert callable(checker)


# =============================================================================
# Authentication Tests
# =============================================================================

class TestAuthenticateUser:
    """Tests for authenticate_user function."""

    @pytest.mark.asyncio
    @patch("dashboard.auth._load_users")
    async def test_authenticate_user_success(self, mock_load):
        """Test successful authentication."""
        from dashboard.auth import authenticate_user, get_password_hash
        
        hashed = get_password_hash("correct_password")
        mock_load.return_value = {
            "testuser": {"hash": hashed, "role": "admin"}
        }
        
        user = await authenticate_user("testuser", "correct_password")
        
        assert user is not None
        assert user.user_id == "testuser"
        assert user.role == "admin"

    @pytest.mark.asyncio
    @patch("dashboard.auth._load_users")
    async def test_authenticate_user_wrong_password(self, mock_load):
        """Test authentication with wrong password."""
        from dashboard.auth import authenticate_user, get_password_hash
        
        hashed = get_password_hash("correct_password")
        mock_load.return_value = {
            "testuser": {"hash": hashed, "role": "admin"}
        }
        
        user = await authenticate_user("testuser", "wrong_password")
        
        assert user is None

    @pytest.mark.asyncio
    @patch("dashboard.auth._load_users")
    async def test_authenticate_user_not_found(self, mock_load):
        """Test authentication for non-existent user."""
        from dashboard.auth import authenticate_user
        
        mock_load.return_value = {
            "otheruser": {"hash": "some_hash", "role": "admin"}
        }
        
        user = await authenticate_user("nonexistent", "password")
        
        assert user is None

    @pytest.mark.asyncio
    @patch("dashboard.auth._load_users")
    async def test_authenticate_user_no_users_configured(self, mock_load):
        """Test authentication when no users are configured."""
        from dashboard.auth import authenticate_user
        
        mock_load.side_effect = RuntimeError("No users")
        
        user = await authenticate_user("anyuser", "password")
        
        assert user is None

    @pytest.mark.asyncio
    @patch("dashboard.auth._load_users")
    async def test_authenticate_user_plaintext_password(self, mock_load):
        """Test authentication with plaintext password (migration)."""
        from dashboard.auth import authenticate_user
        
        # Old format - plaintext password
        mock_load.return_value = {
            "testuser": {"password": "plaintext123", "role": "admin"}
        }
        
        with pytest.warns(auth_module.SecurityWarning):
            user = await authenticate_user("testuser", "plaintext123")
        
        assert user is not None
        assert user.user_id == "testuser"
        assert user.role == "admin"

    @pytest.mark.asyncio
    @patch("dashboard.auth._load_users")
    async def test_authenticate_user_plaintext_wrong_password(self, mock_load):
        """Test authentication with wrong plaintext password."""
        from dashboard.auth import authenticate_user
        
        mock_load.return_value = {
            "testuser": {"password": "correct123", "role": "admin"}
        }
        
        with pytest.warns(auth_module.SecurityWarning):
            user = await authenticate_user("testuser", "wrong123")
        
        assert user is None

    @pytest.mark.asyncio
    @patch("dashboard.auth._load_users")
    async def test_authenticate_user_default_role(self, mock_load):
        """Test authentication assigns default role."""
        from dashboard.auth import authenticate_user, get_password_hash
        
        hashed = get_password_hash("password")
        # User without role specified
        mock_load.return_value = {
            "testuser": {"hash": hashed}
        }
        
        user = await authenticate_user("testuser", "password")
        
        assert user is not None
        assert user.role == "viewer"  # Default role


# =============================================================================
# API Key Tests
# =============================================================================

class TestVerifyApiKey:
    """Tests for verify_api_key function."""

    def test_verify_api_key_correct(self, mock_settings):
        """Test verifying correct API key."""
        from dashboard.auth import verify_api_key
        
        result = verify_api_key("test-api-key-12345")
        assert result is True

    def test_verify_api_key_incorrect(self, mock_settings):
        """Test verifying incorrect API key."""
        from dashboard.auth import verify_api_key
        
        result = verify_api_key("wrong-api-key")
        assert result is False

    def test_verify_api_key_empty(self, mock_settings):
        """Test verifying empty API key."""
        from dashboard.auth import verify_api_key
        
        result = verify_api_key("")
        assert result is False


# =============================================================================
# Security Warning Tests
# =============================================================================

class TestSecurityWarning:
    """Tests for SecurityWarning class."""

    def test_security_warning_is_warning(self):
        """Test that SecurityWarning is a Warning subclass."""
        from dashboard.auth import SecurityWarning
        
        assert issubclass(SecurityWarning, Warning)

    def test_security_warning_can_be_raised(self):
        """Test that SecurityWarning can be raised."""
        from dashboard.auth import SecurityWarning
        
        with pytest.warns(SecurityWarning):
            import warnings
            warnings.warn("Test security warning", SecurityWarning)


# =============================================================================
# Password Migration Tests
# =============================================================================

class TestMigratePasswords:
    """Tests for migrate_passwords function."""

    @patch("dashboard.auth._load_users")
    @patch("builtins.open", mock_open())
    @patch("json.dump")
    @patch("os.getenv")
    def test_migrate_passwords_success(self, mock_getenv, mock_json_dump, mock_load):
        """Test successful password migration."""
        from dashboard.auth import migrate_passwords
        
        # Users with plaintext passwords
        mock_load.return_value = {
            "admin": {"password": "admin123", "role": "admin"},
            "viewer": {"password": "view456", "role": "viewer"}
        }
        mock_getenv.return_value = "/tmp/migrated_users.json"
        
        migrate_passwords()
        
        # Check that json.dump was called with hashed passwords
        assert mock_json_dump.called
        migrated_users = mock_json_dump.call_args[0][0]
        
        assert "admin" in migrated_users
        assert "hash" in migrated_users["admin"]
        assert migrated_users["admin"]["hash"].startswith("$")  # bcrypt hash

    @patch("dashboard.auth._load_users")
    def test_migrate_passwords_no_plaintext(self, mock_load):
        """Test migration when no plaintext passwords exist."""
        from dashboard.auth import migrate_passwords
        
        # Users already have hashed passwords
        mock_load.return_value = {
            "admin": {"hash": "$2b$12$...", "role": "admin"}
        }
        
        # Should complete without error
        migrate_passwords()

    @patch("dashboard.auth._load_users")
    def test_migrate_passwords_no_users(self, mock_load):
        """Test migration when no users exist."""
        from dashboard.auth import migrate_passwords
        
        mock_load.side_effect = RuntimeError("No users")
        
        # Should complete without error
        migrate_passwords()


# =============================================================================
# Bcrypt Truncation Tests
# =============================================================================

class TestBcryptTruncation:
    """Tests for bcrypt password truncation."""

    def test_truncate_short_password(self):
        """Test that short passwords work normally."""
        from dashboard.auth import get_password_hash, verify_password
        
        password = "short"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True

    def test_truncate_long_password(self):
        """Test that long passwords are truncated to 72 bytes."""
        from dashboard.auth import get_password_hash, verify_password
        
        # Password longer than 72 bytes
        password = "a" * 100
        hashed = get_password_hash(password)
        
        # Should still verify
        assert verify_password(password, hashed) is True

    def test_truncate_unicode_password(self):
        """Test that unicode passwords are handled correctly."""
        from dashboard.auth import get_password_hash, verify_password
        
        # Unicode password
        password = "пароль" * 20  # Russian word "password" repeated
        hashed = get_password_hash(password)
        
        # Should still verify
        assert verify_password(password, hashed) is True
