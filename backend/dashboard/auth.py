"""
Authentication and session management for the SaaS dashboard using Privy.

Implements:
- Privy OAuth-based authentication (email, social logins)
- Redis-backed sessions (survive restarts, work across processes)
- CSRF token protection
- 30-minute inactivity timeout, 8-hour max session
- Server-side encryption key management
"""

import os
import json
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

from fastapi import HTTPException, status, Depends, Request, Response
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from backend.dashboard.config import get_dashboard_settings
from shared.security.encryption import (
    generate_dek, encrypt_dek, decrypt_dek,
    EncryptionManager, EncryptionError, DecryptionError
)

# Security scheme for API documentation
security = HTTPBearer(auto_error=False)


class SessionError(Exception):
    """Base exception for session errors."""
    pass


class InvalidSessionError(SessionError):
    """Raised when session is invalid or expired."""
    pass


class CSRFError(SessionError):
    """Raised when CSRF token validation fails."""
    pass


# Session TTL constants
INACTIVITY_TIMEOUT_SECONDS = 30 * 60  # 30 minutes
MAX_SESSION_SECONDS = 8 * 60 * 60     # 8 hours
SESSION_REDIS_PREFIX = "session:"


@dataclass
class Session:
    """Active session holding encryption manager."""
    id: str
    privy_user_id: str
    email: Optional[str]
    created_at: datetime
    expires_at: datetime
    last_activity: datetime
    csrf_token: str
    ip_address: str
    user_agent: str
    encryption_manager: EncryptionManager = field(default_factory=lambda: EncryptionManager())

    # Class constants
    INACTIVITY_TIMEOUT_MINUTES = 30
    MAX_SESSION_HOURS = 8

    @property
    def is_expired(self) -> bool:
        """Check if session has exceeded max lifetime."""
        return datetime.utcnow() > self.expires_at

    @property
    def is_inactive(self) -> bool:
        """Check if session has timed out due to inactivity."""
        timeout = timedelta(minutes=self.INACTIVITY_TIMEOUT_MINUTES)
        return datetime.utcnow() > self.last_activity + timeout

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()

    def to_json(self) -> str:
        """Serialize session metadata to JSON (for Redis)."""
        return json.dumps({
            "id": self.id,
            "privy_user_id": self.privy_user_id,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "csrf_token": self.csrf_token,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        })

    @classmethod
    def from_json(cls, data: str) -> "Session":
        """Deserialize session from JSON."""
        d = json.loads(data)
        return cls(
            id=d["id"],
            privy_user_id=d["privy_user_id"],
            email=d.get("email"),
            created_at=datetime.fromisoformat(d["created_at"]),
            expires_at=datetime.fromisoformat(d["expires_at"]),
            last_activity=datetime.fromisoformat(d["last_activity"]),
            csrf_token=d["csrf_token"],
            ip_address=d["ip_address"],
            user_agent=d["user_agent"],
        )


class PrivyAuth:
    """
    Privy authentication handler using the official SDK.

    Wraps the PrivyClient for token verification and user management.
    """

    def __init__(self, app_id: Optional[str] = None, app_secret: Optional[str] = None):
        from backend.dashboard.privy_client import PrivyClient

        self._client: Optional[PrivyClient] = None
        self._app_id = app_id
        self._app_secret = app_secret

    @property
    def client(self):
        """Lazy-load the Privy client."""
        if self._client is None:
            from backend.dashboard.privy_client import PrivyClient
            self._client = PrivyClient(
                app_id=self._app_id,
                app_secret=self._app_secret
            )
        return self._client

    async def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify a Privy access token."""
        try:
            user_data = await self.client.verify_access_token(token)
            return {
                "id": user_data["id"],
                "email": user_data.get("email"),
                "wallet_address": user_data.get("wallet_address"),
            }
        except Exception as e:
            raise SessionError(f"Invalid Privy token: {e}") from e

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user info by ID."""
        return await self.client.get_user(user_id)


class SessionManager:
    """
    Manages active sessions using Redis for persistence.

    Sessions are stored in Redis with TTL matching the max session lifetime.
    In-process encryption managers are cached for the current process only.
    """

    def __init__(self):
        self._encryption_managers: Dict[str, EncryptionManager] = {}
        self._db = None

    def set_db(self, db):
        """Set database connection."""
        self._db = db

    async def _get_redis(self):
        from shared.redis_client import get_redis
        return await get_redis()

    def _derive_kek(self, privy_user_id: str, server_secret: str) -> bytes:
        """Derive KEK from Privy user ID and server secret."""
        return hmac.new(
            server_secret.encode(),
            privy_user_id.encode(),
            hashlib.sha256
        ).digest()

    async def create_session(
        self,
        privy_user_id: str,
        email: Optional[str],
        ip_address: str,
        user_agent: str,
        server_secret: str
    ) -> Session:
        """Create a new session after successful Privy authentication."""
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)

        now = datetime.utcnow()
        expires_at = now + timedelta(hours=Session.MAX_SESSION_HOURS)

        session = Session(
            id=session_id,
            privy_user_id=privy_user_id,
            email=email,
            created_at=now,
            expires_at=expires_at,
            last_activity=now,
            csrf_token=csrf_token,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Derive KEK and unlock encryption
        kek = self._derive_kek(privy_user_id, server_secret)

        # Get or create DEK
        encrypted_dek = await self._get_or_create_dek(privy_user_id, kek)
        session.encryption_manager.unlock_with_dek(encrypted_dek, kek)

        # Store in Redis with TTL
        redis = await self._get_redis()
        redis_key = f"{SESSION_REDIS_PREFIX}{session_id}"
        await redis.set(redis_key, session.to_json(), ex=MAX_SESSION_SECONDS)

        # Cache encryption manager in-process
        self._encryption_managers[session_id] = session.encryption_manager

        # Store metadata in database (NOT the KEK or DEK!)
        if self._db:
            await self._db.execute(
                """INSERT INTO sessions
                   (id, privy_user_id, email, created_at, expires_at, csrf_token, ip_address, user_agent)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                (session_id, privy_user_id, email, now,
                 expires_at, csrf_token, ip_address, user_agent)
            )

        return session

    async def _get_or_create_dek(self, privy_user_id: str, kek: bytes) -> bytes:
        """Get existing DEK or create new one."""
        if self._db:
            row = await self._db.fetchone(
                "SELECT encrypted_dek FROM user_keys WHERE privy_user_id = $1",
                (privy_user_id,)
            )
            if row and row.get("encrypted_dek"):
                return row["encrypted_dek"]

        # Create new DEK
        dek = generate_dek()
        salt = secrets.token_bytes(32)
        encrypted_dek = encrypt_dek(dek, kek, salt)

        # Store encrypted DEK
        if self._db:
            await self._db.execute(
                """INSERT INTO user_keys
                   (privy_user_id, encrypted_dek, created_at)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (privy_user_id) DO UPDATE SET
                   encrypted_dek = EXCLUDED.encrypted_dek""",
                (privy_user_id, encrypted_dek, datetime.utcnow())
            )

        return encrypted_dek

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID from Redis, checking validity."""
        redis = await self._get_redis()
        redis_key = f"{SESSION_REDIS_PREFIX}{session_id}"

        data = await redis.get(redis_key)
        if data is None:
            # Session not in Redis — expired or never existed
            self._encryption_managers.pop(session_id, None)
            return None

        session = Session.from_json(data)

        # Check expiry
        if session.is_expired:
            await self.destroy_session(session_id)
            raise InvalidSessionError("Session expired - please log in again")

        if session.is_inactive:
            await self.destroy_session(session_id)
            raise InvalidSessionError("Session timed out due to inactivity")

        # Restore encryption manager from in-process cache
        em = self._encryption_managers.get(session_id)
        if em:
            session.encryption_manager = em

        return session

    async def validate_csrf(self, session_id: str, csrf_token: str) -> bool:
        """Validate CSRF token for session."""
        session = await self.get_session(session_id)
        if not session:
            return False
        return secrets.compare_digest(session.csrf_token, csrf_token)

    async def touch_session(self, session_id: str) -> None:
        """Update last activity timestamp in Redis."""
        redis = await self._get_redis()
        redis_key = f"{SESSION_REDIS_PREFIX}{session_id}"

        data = await redis.get(redis_key)
        if data:
            session = Session.from_json(data)
            session.touch()
            # Reset TTL based on remaining max session time
            remaining = int((session.expires_at - datetime.utcnow()).total_seconds())
            if remaining > 0:
                await redis.set(redis_key, session.to_json(), ex=remaining)

    async def destroy_session(self, session_id: str) -> None:
        """Destroy a session (logout)."""
        # Remove from Redis
        redis = await self._get_redis()
        await redis.delete(f"{SESSION_REDIS_PREFIX}{session_id}")

        # Remove in-process encryption manager
        em = self._encryption_managers.pop(session_id, None)
        if em:
            em.lock()

        # Remove from DB
        if self._db:
            await self._db.execute(
                "DELETE FROM sessions WHERE id = $1",
                (session_id,)
            )

    async def cleanup_expired(self) -> int:
        """Clean up expired sessions. Redis TTL handles most of this automatically."""
        # In-process cleanup of encryption managers
        expired = []
        redis = await self._get_redis()

        for session_id in list(self._encryption_managers.keys()):
            exists = await redis.exists(f"{SESSION_REDIS_PREFIX}{session_id}")
            if not exists:
                expired.append(session_id)

        for session_id in expired:
            em = self._encryption_managers.pop(session_id, None)
            if em:
                em.lock()

        return len(expired)


# Global session manager
session_manager = SessionManager()


# Cookie helpers
SESSION_COOKIE_NAME = "session_id"
CSRF_COOKIE_NAME = "csrf_token"


def _is_production() -> bool:
    """Check if running in production environment."""
    settings = get_dashboard_settings()
    return settings.dashboard_env == "production"


def set_session_cookie(response: Response, session_id: str, secure: Optional[bool] = None) -> None:
    """Set HTTP-only session cookie."""
    if secure is None:
        secure = _is_production()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=8 * 60 * 60,  # 8 hours
        path="/"
    )


def set_csrf_cookie(response: Response, csrf_token: str, secure: Optional[bool] = None) -> None:
    """Set CSRF token cookie (not HTTP-only, accessible by JS)."""
    if secure is None:
        secure = _is_production()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # JS needs to read this
        secure=secure,
        samesite="strict",
        max_age=8 * 60 * 60,
        path="/"
    )


def clear_session_cookies(response: Response) -> None:
    """Clear session cookies."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


# Dependencies for FastAPI
async def get_current_session(request: Request) -> Session:
    """Dependency to get current valid session."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid session",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Update activity
        await session_manager.touch_session(session_id)

        return session

    except InvalidSessionError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_csrf(request: Request) -> None:
    """Dependency to validate CSRF token."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    csrf_token = request.headers.get("X-CSRF-Token")

    if not session_id or not csrf_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token required"
        )

    valid = await session_manager.validate_csrf(session_id, csrf_token)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token"
        )


async def get_encryption_manager(session: Session = Depends(get_current_session)) -> EncryptionManager:
    """Dependency to get encryption manager for current session."""
    if not session.encryption_manager.is_unlocked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Encryption not unlocked"
        )
    return session.encryption_manager


# Pydantic models for API
class User(BaseModel):
    """Authenticated user."""
    user_id: str  # Privy user ID
    email: Optional[str] = None
    role: str = "admin"


async def get_current_user(session: Session = Depends(get_current_session)) -> User:
    """Get current authenticated user."""
    return User(
        user_id=session.privy_user_id,
        email=session.email,
        role="admin"
    )


def require_role(required_roles: list):
    """Dependency factory to require specific roles.

    Checks the user's actual role against required_roles.
    For now, all users default to 'admin' until role column is added to users table.
    """
    async def role_checker(session: Session = Depends(get_current_session)):
        # TODO: Load role from users table once role column is added
        user_role = "admin"

        if user_role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return User(user_id=session.privy_user_id, email=session.email, role=user_role)
    return role_checker


# Predefined role dependencies
require_admin = require_role(["admin"])
require_operator = require_role(["admin", "operator"])
require_viewer = require_role(["admin", "operator", "viewer"])


def verify_api_key(api_key: str) -> bool:
    """Verify bot admin API key using constant-time comparison."""
    settings = get_dashboard_settings()
    if not settings.bot_admin_key:
        return False
    return secrets.compare_digest(api_key, settings.bot_admin_key)


# Backward compatibility - legacy models
class TokenData(BaseModel):
    """JWT token payload (legacy)."""
    user_id: str
    role: str
    exp: datetime
