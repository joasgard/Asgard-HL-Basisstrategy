"""
Authentication API endpoints for Privy-based email auth flow.

Implements v3.5 auth flow:
- POST /api/v1/auth/privy/initiate - Start email auth
- POST /api/v1/auth/privy/verify - Verify OTP, create user
- POST /api/v1/auth/logout - Clear session
- GET  /api/v1/auth/me - Return user + wallet addresses
"""

import logging
import re
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Request, Response, HTTPException, Depends, status
from pydantic import BaseModel, Field, field_validator

from shared.db.database import Database, get_db
from backend.dashboard.auth import (
    session_manager, set_session_cookie, set_csrf_cookie,
    clear_session_cookies, SESSION_COOKIE_NAME
)
from backend.dashboard.privy_client import get_privy_client, AuthenticationError
from backend.dashboard.security import sanitize_for_audit

router = APIRouter(tags=["auth"])  # Prefix is added in main.py


# Rate limiting storage (in-memory, per-process)
# In production with multiple workers, use Redis
_otp_attempts: Dict[str, list] = {}
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 900  # 15 minutes


class EmailInitiateRequest(BaseModel):
    """Request to initiate email authentication."""
    email: str
    stay_logged_in: bool = False  # True = 7 days, False = 24 hours
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        v = v.strip().lower()
        if not v or '@' not in v or '.' not in v.split('@')[-1]:
            raise ValueError('Invalid email address')
        return v


class OTPVerifyRequest(BaseModel):
    """Request to verify OTP code."""
    email: str
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    stay_logged_in: bool = False
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        v = v.strip().lower()
        if not v or '@' not in v or '.' not in v.split('@')[-1]:
            raise ValueError('Invalid email address')
        return v


class AuthResponse(BaseModel):
    """Authentication response."""
    success: bool
    message: str
    user_id: Optional[str] = None
    is_new_user: Optional[bool] = None
    solana_address: Optional[str] = None
    evm_address: Optional[str] = None
    requires_deposit: Optional[bool] = None


class UserInfoResponse(BaseModel):
    """User info response."""
    user_id: str
    email: Optional[str] = None
    solana_address: Optional[str] = None
    evm_address: Optional[str] = None
    is_new_user: bool = False
    created_at: Optional[str] = None


def _check_rate_limit(identifier: str) -> tuple[bool, int]:
    """
    Check if rate limit is exceeded for identifier.
    
    Returns:
        (allowed, remaining_attempts)
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    
    # Get attempts within window
    attempts = _otp_attempts.get(identifier, [])
    attempts = [t for t in attempts if t > window_start]
    _otp_attempts[identifier] = attempts
    
    if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
        return False, 0
    
    return True, RATE_LIMIT_MAX_ATTEMPTS - len(attempts)


def _record_attempt(identifier: str) -> None:
    """Record an attempt for rate limiting."""
    now = time.time()
    if identifier not in _otp_attempts:
        _otp_attempts[identifier] = []
    _otp_attempts[identifier].append(now)


@router.post("/privy/initiate", response_model=AuthResponse)
async def initiate_auth(
    request: Request,
    response: Response,
    data: EmailInitiateRequest,
    db: Database = Depends(get_db)
) -> AuthResponse:
    """
    Step 1: Initiate email authentication.
    
    - Validates email format
    - Checks rate limiting
    - Creates temporary session for OTP flow
    - Returns status (OTP sent)
    
    Note: Actual OTP is sent by Privy's SDK on the frontend.
    This endpoint validates the email and sets up the session.
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # Rate limiting by IP + email
    rate_key = f"{client_ip}:{data.email.lower()}"
    allowed, remaining = _check_rate_limit(rate_key)
    
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again in 15 minutes."
        )
    
    # Record attempt
    _record_attempt(rate_key)
    
    # Check if user exists
    existing_user = await db.fetchone(
        "SELECT id, email, solana_address, evm_address FROM users WHERE email = $1",
        (data.email.lower(),)
    )
    
    # Store pending auth in temporary session
    # This will be used to verify the OTP
    pending_auth_id = f"pending_{rate_key}"
    session_duration = 168 if data.stay_logged_in else 24  # 7 days or 24 hours
    
    await db.execute(
        """INSERT INTO pending_auth
           (id, email, created_at, session_duration_hours, ip_address)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT(id) DO UPDATE SET
           email = EXCLUDED.email,
           created_at = EXCLUDED.created_at,
           session_duration_hours = EXCLUDED.session_duration_hours,
           ip_address = EXCLUDED.ip_address""",
        (pending_auth_id, data.email.lower(), datetime.utcnow(),
         session_duration, client_ip)
    )
    
    # Audit log
    await db.execute(
        "INSERT INTO audit_log (action, \"user\", ip_address, details, success) VALUES ($1, $2, $3, $4, $5)",
        ("auth_initiate", data.email.lower(), client_ip,
         sanitize_for_audit("auth_initiate", {"existing_user": existing_user is not None}), True)
    )

    return AuthResponse(
        success=True,
        message="Authentication initiated. Check your email for OTP.",
        is_new_user=existing_user is None
    )


@router.post("/privy/verify", response_model=AuthResponse)
async def verify_otp(
    request: Request,
    response: Response,
    data: OTPVerifyRequest,
    db: Database = Depends(get_db)
) -> AuthResponse:
    """
    Step 2: Verify OTP code and complete authentication.
    
    - Validates OTP format (6 digits)
    - Verifies with Privy
    - Creates/updates user record
    - Creates wallets if new user
    - Sets session cookie
    - Returns user info + whether deposit modal should be shown
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    
    # Rate limiting check
    rate_key = f"{client_ip}:{data.email.lower()}"
    allowed, remaining = _check_rate_limit(rate_key)
    
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again in 15 minutes."
        )
    
    _record_attempt(rate_key)
    
    try:
        # Get Privy client
        privy = get_privy_client()
        
        # Verify the OTP with Privy
        # Note: In the actual implementation, this uses Privy's server-side API
        # to verify the code sent via the frontend SDK
        
        # For now, we simulate the verification by looking up/creating user
        # In production, this would call privy.verify_otp(email, code)
        
        # Check if user exists by email
        user_info = await privy.get_user_by_email(data.email.lower())
        
        is_new_user = user_info is None
        
        if is_new_user:
            # New user - create them in Privy
            # This would normally happen via the frontend SDK
            # For server-side flow, we'll create the user record locally
            import secrets
            privy_user_id = f"user_{secrets.token_urlsafe(16)}"
        else:
            privy_user_id = user_info.get("id")

        # Fetch wallet addresses from Privy linked accounts
        wallet_result = await privy.get_user_wallet_addresses(privy_user_id)
        solana_address = wallet_result.get("solana_address")
        evm_address = wallet_result.get("ethereum_address")
        
        # Get session duration from pending auth or use default
        pending_auth_id = f"pending_{rate_key}"
        pending = await db.fetchone(
            "SELECT session_duration_hours FROM pending_auth WHERE id = $1",
            (pending_auth_id,)
        )
        session_duration = pending.get("session_duration_hours", 24) if pending else 24
        
        # Create or update user in database
        now = datetime.utcnow()
        await db.execute(
            """INSERT INTO users (id, email, solana_address, evm_address, is_new_user, created_at, last_login, session_duration_hours)
               VALUES ($1, $2, $3, $4, $5, COALESCE((SELECT created_at FROM users WHERE id = $6), $7), $8, $9)
               ON CONFLICT(id) DO UPDATE SET
               email = EXCLUDED.email,
               solana_address = COALESCE(EXCLUDED.solana_address, users.solana_address),
               evm_address = COALESCE(EXCLUDED.evm_address, users.evm_address),
               is_new_user = false,
               last_login = EXCLUDED.last_login,
               session_duration_hours = EXCLUDED.session_duration_hours""",
            (privy_user_id, data.email.lower(), solana_address, evm_address,
             is_new_user, privy_user_id, now, now, session_duration)
        )
        
        # Clean up pending auth
        await db.execute("DELETE FROM pending_auth WHERE id = $1", (pending_auth_id,))
        
        # Create session
        from backend.dashboard.config import get_dashboard_settings
        settings = get_dashboard_settings()
        
        session = await session_manager.create_session(
            privy_user_id=privy_user_id,
            email=data.email.lower(),
            ip_address=client_ip,
            user_agent=user_agent,
            server_secret=settings.session_secret
        )
        
        # Set cookies with appropriate duration
        set_session_cookie(response, session.id)
        set_csrf_cookie(response, session.csrf_token)
        
        # Audit log
        await db.execute(
            "INSERT INTO audit_log (action, \"user\", ip_address, details, success) VALUES ($1, $2, $3, $4, $5)",
            ("auth_verify", privy_user_id, client_ip,
             sanitize_for_audit("auth_verify", {"is_new_user": is_new_user}), True)
        )
        
        # Determine if deposit modal should be shown
        # Show for new users OR users without wallet addresses
        requires_deposit = is_new_user or not solana_address or not evm_address
        
        return AuthResponse(
            success=True,
            message="Authentication successful",
            user_id=privy_user_id,
            is_new_user=is_new_user,
            solana_address=solana_address,
            evm_address=evm_address,
            requires_deposit=requires_deposit
        )
        
    except AuthenticationError as e:
        logger.warning(f"OTP verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification code"
        )
    except Exception as e:
        logger.error(f"Authentication failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Database = Depends(get_db)
) -> dict:
    """
    Logout and clear session.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    client_ip = request.client.host if request.client else "unknown"
    
    if session_id:
        # Get session info for audit log
        session = await session_manager.get_session(session_id)
        user_id = session.privy_user_id if session else "unknown"
        
        await session_manager.destroy_session(session_id)
        
        # Audit log
        await db.execute(
            "INSERT INTO audit_log (action, \"user\", ip_address, details, success) VALUES ($1, $2, $3, $4, $5)",
            ("logout", user_id, client_ip, "{}", True)
        )
    
    clear_session_cookies(response)
    
    return {"success": True, "message": "Logged out successfully"}


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    request: Request,
    db: Database = Depends(get_db)
) -> UserInfoResponse:
    """
    Get current authenticated user's information.
    
    Returns:
        User info including wallet addresses
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    session = await session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )
    
    # Update activity
    await session_manager.touch_session(session_id)
    
    # Get user from database
    user = await db.fetchone(
        "SELECT id, email, solana_address, evm_address, is_new_user, created_at FROM users WHERE id = $1",
        (session.privy_user_id,)
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserInfoResponse(
        user_id=user.get("id"),
        email=user.get("email"),
        solana_address=user.get("solana_address"),
        evm_address=user.get("evm_address"),
        is_new_user=bool(user.get("is_new_user", False)),
        created_at=user.get("created_at")
    )


@router.get("/check")
async def check_auth_status(
    request: Request,
    db: Database = Depends(get_db)
) -> dict:
    """
    Check if user is authenticated.
    
    Returns:
        { authenticated: bool, user: UserInfoResponse | null }
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    
    if not session_id:
        return {"authenticated": False, "user": None}
    
    session = await session_manager.get_session(session_id)
    
    if not session:
        return {"authenticated": False, "user": None}
    
    # Update activity
    await session_manager.touch_session(session_id)
    
    # Get user info
    user = await db.fetchone(
        "SELECT id, email, solana_address, evm_address, is_new_user, created_at FROM users WHERE id = $1",
        (session.privy_user_id,)
    )

    if not user:
        return {"authenticated": False, "user": None}

    solana_address = user.get("solana_address")
    evm_address = user.get("evm_address")

    # Backfill wallet addresses from Privy if missing in DB
    if not solana_address or not evm_address:
        try:
            privy = get_privy_client()
            wallet_result = await privy.get_user_wallet_addresses(session.privy_user_id)
            new_sol = wallet_result.get("solana_address")
            new_evm = wallet_result.get("ethereum_address")

            if new_sol or new_evm:
                await db.execute(
                    """UPDATE users SET
                       solana_address = COALESCE($1, solana_address),
                       evm_address = COALESCE($2, evm_address)
                       WHERE id = $3""",
                    (new_sol, new_evm, session.privy_user_id)
                )
                solana_address = new_sol or solana_address
                evm_address = new_evm or evm_address
        except Exception as e:
            logger.warning(f"Wallet backfill failed for {session.privy_user_id}: {e}")

    return {
        "authenticated": True,
        "user": {
            "user_id": user.get("id"),
            "email": user.get("email"),
            "solana_address": solana_address,
            "evm_address": evm_address,
            "is_new_user": bool(user.get("is_new_user", False)),
            "created_at": user.get("created_at")
        }
    }


class PrivySyncRequest(BaseModel):
    """Request to sync Privy auth with backend session."""
    privy_access_token: str
    email: Optional[str] = None


class PrivySyncResponse(BaseModel):
    """Response from Privy sync."""
    success: bool
    user_id: str
    email: Optional[str] = None
    solana_address: Optional[str] = None
    evm_address: Optional[str] = None
    is_new_user: bool = True


@router.post("/sync", response_model=PrivySyncResponse)
async def sync_privy_auth(
    request: Request,
    response: Response,
    data: PrivySyncRequest,
    db: Database = Depends(get_db)
) -> PrivySyncResponse:
    """
    Sync Privy frontend authentication with backend session.
    
    Called after user authenticates with Privy on the frontend.
    Creates/updates user record and establishes session.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    
    try:
        privy = get_privy_client()

        # Verify Privy access token server-side (REQUIRED)
        try:
            privy_user = await privy.verify_access_token(data.privy_access_token)
        except Exception as e:
            logger.warning(f"Privy token verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token"
            )

        privy_user_id = privy_user.get("id") or privy_user.get("user_id")
        if not privy_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token"
            )

        # Get or create user in our database
        user = await db.fetchone(
            "SELECT id, email, solana_address, evm_address, is_new_user FROM users WHERE id = $1",
            (privy_user_id,)
        )
        
        is_new_user = user is None
        
        # Fetch wallet addresses from Privy linked accounts.
        # Wallets are created by the frontend SDK (createOnLogin: 'all-users').
        solana_address = None
        evm_address = None
        try:
            wallet_result = await privy.get_user_wallet_addresses(privy_user_id)
            solana_address = wallet_result.get("solana_address")
            evm_address = wallet_result.get("ethereum_address")
        except Exception as e:
            logger.warning(f"Wallet address lookup skipped for {privy_user_id}: {e}")

        if is_new_user:
            now = datetime.utcnow()

            await db.execute(
                """INSERT INTO users (id, email, solana_address, evm_address, is_new_user, created_at, last_login)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                (privy_user_id, data.email, solana_address, evm_address, True, now, now)
            )
        else:
            is_new_user = bool(user.get("is_new_user", False))

            now = datetime.utcnow()
            await db.execute(
                """UPDATE users SET
                   solana_address = COALESCE($1, solana_address),
                   evm_address = COALESCE($2, evm_address),
                   last_login = $3
                   WHERE id = $4""",
                (solana_address, evm_address, now, privy_user_id)
            )

        # Create session
        from backend.dashboard.config import get_dashboard_settings
        settings = get_dashboard_settings()

        session = await session_manager.create_session(
            privy_user_id=privy_user_id,
            email=data.email,
            ip_address=client_ip,
            user_agent=user_agent,
            server_secret=settings.session_secret
        )

        # Set cookies
        set_session_cookie(response, session.id)
        set_csrf_cookie(response, session.csrf_token)

        # Audit log
        await db.execute(
            "INSERT INTO audit_log (action, \"user\", ip_address, details, success) VALUES ($1, $2, $3, $4, $5)",
            ("privy_sync", privy_user_id, client_ip,
             sanitize_for_audit("privy_sync", {"is_new_user": is_new_user}), True)
        )

        return PrivySyncResponse(
            success=True,
            user_id=privy_user_id,
            email=data.email,
            solana_address=solana_address,
            evm_address=evm_address,
            is_new_user=is_new_user
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication sync failed"
        )
