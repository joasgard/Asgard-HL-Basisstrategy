"""
Authentication and session management for the SaaS dashboard using Privy.

Implements:
- Privy OAuth-based authentication (email, social logins)
- Session-based auth with HTTP-only cookies
- CSRF token protection
- 30-minute inactivity timeout, 8-hour max session
- Server-side encryption key management (single-tenant model)
"""

import os
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

from fastapi import HTTPException, status, Depends, Request, Response
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from src.dashboard.config import get_dashboard_settings
from src.security.encryption import (
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


class PrivyAuth:
    """Privy authentication handler."""
    
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.api_url = "https://auth.privy.io"
    
    async def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify a Privy ID token (from OAuth callback).
        
        Returns:
            User info dict with 'id', 'email', etc.
        """
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {token}",
                "privy-app-id": self.app_id
            }
            async with session.get(
                f"{self.api_url}/api/v1/sessions/me",
                headers=headers
            ) as response:
                if response.status != 200:
                    raise SessionError("Invalid Privy token")
                return await response.json()
    
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user info by ID."""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Basic {self._get_auth_header()}",
                "privy-app-id": self.app_id
            }
            async with session.get(
                f"{self.api_url}/api/v1/users/{user_id}",
                headers=headers
            ) as response:
                if response.status == 200:
                    return await response.json()
                return None
    
    def _get_auth_header(self) -> str:
        """Get base64 encoded app credentials."""
        import base64
        credentials = f"{self.app_id}:{self.app_secret}"
        return base64.b64encode(credentials.encode()).decode()


class SessionManager:
    """Manages active sessions in memory and database."""
    
    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._db = None  # Will be set when DB module is ready
    
    def set_db(self, db):
        """Set database connection."""
        self._db = db
    
    def _derive_kek(self, privy_user_id: str, server_secret: str) -> bytes:
        """
        Derive KEK from Privy user ID and server secret.
        This ensures only this specific user+server combo can decrypt.
        """
        # Use HMAC-SHA256 to derive key
        key_material = f"{privy_user_id}:{server_secret}"
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
        """
        Create a new session after successful Privy authentication.
        
        Args:
            privy_user_id: Privy user ID
            email: User's email
            ip_address: Client IP for binding
            user_agent: Client user agent
            server_secret: Server secret for KEK derivation
            
        Returns:
            New Session object with unlocked encryption
        """
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
        
        # Store in memory
        self._sessions[session_id] = session
        
        # Store metadata in database (NOT the KEK or DEK!)
        if self._db:
            await self._db.execute(
                """INSERT INTO sessions 
                   (id, privy_user_id, email, created_at, expires_at, csrf_token, ip_address, user_agent) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, privy_user_id, email, now.isoformat(), 
                 expires_at.isoformat(), csrf_token, ip_address, user_agent)
            )
        
        return session
    
    async def _get_or_create_dek(self, privy_user_id: str, kek: bytes) -> bytes:
        """Get existing DEK or create new one."""
        if self._db:
            row = await self._db.fetchone(
                "SELECT encrypted_dek FROM user_keys WHERE privy_user_id = ?",
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
                """INSERT OR REPLACE INTO user_keys 
                   (privy_user_id, encrypted_dek, created_at) 
                   VALUES (?, ?, ?)""",
                (privy_user_id, encrypted_dek, datetime.utcnow().isoformat())
            )
        
        return encrypted_dek
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID, checking validity."""
        session = self._sessions.get(session_id)
        
        if session is None:
            # Session not in memory - user needs to re-authenticate
            return None
        
        # Check expiry
        if session.is_expired:
            await self.destroy_session(session_id)
            raise InvalidSessionError("Session expired - please log in again")
        
        if session.is_inactive:
            await self.destroy_session(session_id)
            raise InvalidSessionError("Session timed out due to inactivity")
        
        return session
    
    async def validate_csrf(self, session_id: str, csrf_token: str) -> bool:
        """Validate CSRF token for session."""
        session = await self.get_session(session_id)
        if not session:
            return False
        return secrets.compare_digest(session.csrf_token, csrf_token)
    
    async def touch_session(self, session_id: str) -> None:
        """Update last activity timestamp."""
        session = self._sessions.get(session_id)
        if session:
            session.touch()
            if self._db:
                await self._db.execute(
                    "UPDATE sessions SET last_activity = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), session_id)
                )
    
    async def destroy_session(self, session_id: str) -> None:
        """Destroy a session (logout)."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.encryption_manager.lock()
        
        if self._db:
            await self._db.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,)
            )
    
    async def cleanup_expired(self) -> int:
        """Clean up expired sessions. Returns count removed."""
        expired = []
        
        for session_id, session in self._sessions.items():
            if session.is_expired or session.is_inactive:
                expired.append(session_id)
        
        for session_id in expired:
            await self.destroy_session(session_id)
        
        return len(expired)


# Global session manager
session_manager = SessionManager()


# Cookie helpers
SESSION_COOKIE_NAME = "session_id"
CSRF_COOKIE_NAME = "csrf_token"


def set_session_cookie(response: Response, session_id: str) -> None:
    """Set HTTP-only session cookie."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=True,  # HTTPS only
        samesite="strict",
        max_age=8 * 60 * 60,  # 8 hours
        path="/"
    )


def set_csrf_cookie(response: Response, csrf_token: str) -> None:
    """Set CSRF token cookie (not HTTP-only, accessible by JS)."""
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # JS needs to read this
        secure=True,
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
    """
    Dependency to get current valid session.
    
    Raises:
        HTTPException: If session is invalid or expired
    """
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
    """
    Dependency to validate CSRF token.
    
    Expects token in X-CSRF-Token header.
    """
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
    role: str = "admin"  # SaaS model: single admin user per instance


async def get_current_user(session: Session = Depends(get_current_session)) -> User:
    """Get current authenticated user."""
    return User(
        user_id=session.privy_user_id,
        email=session.email,
        role="admin"
    )


def require_role(required_roles: list):
    """Dependency factory to require specific roles."""
    async def role_checker(session: Session = Depends(get_current_session)):
        # In SaaS model, single admin has all roles
        if "admin" not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return User(user_id=session.privy_user_id, email=session.email, role="admin")
    return role_checker


# Predefined role dependencies
require_admin = require_role(["admin"])
require_operator = require_role(["admin", "operator"])
require_viewer = require_role(["admin", "operator", "viewer"])


def verify_api_key(api_key: str) -> bool:
    """Verify bot admin API key."""
    settings = get_dashboard_settings()
    return api_key == settings.bot_admin_key


# Backward compatibility - legacy models
class TokenData(BaseModel):
    """JWT token payload (legacy)."""
    user_id: str
    role: str
    exp: datetime
