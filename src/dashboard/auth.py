"""
Authentication and authorization for dashboard.
JWT tokens and API key validation with bcrypt hashing.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel
import bcrypt

from src.dashboard.config import get_dashboard_settings

security = HTTPBearer()


class TokenData(BaseModel):
    """JWT token payload."""
    user_id: str
    role: str  # viewer, operator, admin
    exp: datetime


class User(BaseModel):
    """Authenticated user."""
    user_id: str
    role: str


# User storage - loaded from environment or file
_user_store: Optional[Dict] = None


def _load_users() -> Dict:
    """Load users from environment variable or secrets file."""
    global _user_store
    
    if _user_store is not None:
        return _user_store
    
    # Option 1: Load from environment variable (JSON string)
    users_env = os.getenv("DASHBOARD_USERS")
    if users_env:
        try:
            _user_store = json.loads(users_env)
            return _user_store
        except json.JSONDecodeError:
            raise RuntimeError("DASHBOARD_USERS environment variable contains invalid JSON")
    
    # Option 2: Load from secrets file
    users_file = os.getenv("DASHBOARD_USERS_FILE", "secrets/dashboard_users.json")
    if os.path.exists(users_file):
        try:
            with open(users_file, 'r') as f:
                _user_store = json.load(f)
            return _user_store
        except (json.JSONDecodeError, IOError) as e:
            raise RuntimeError(f"Failed to load users from {users_file}: {e}")
    
    # Option 3: In development mode only, create from individual secrets
    settings = get_dashboard_settings()
    env = os.getenv("DASHBOARD_ENV", "development")
    
    if env == "development":
        # Development fallback - create from legacy password files if they exist
        # This maintains backward compatibility during migration
        import warnings
        warnings.warn(
            "Using development user fallback. Set DASHBOARD_USERS for production.",
            RuntimeWarning
        )
        
        _user_store = {}
        
        # Check for legacy password files
        for role in ["admin", "operator", "viewer"]:
            pw_file = f"secrets/dashboard_{role}_password.txt"
            if os.path.exists(pw_file):
                with open(pw_file, 'r') as f:
                    password = f.read().strip()
                    # Hash the password for storage
                    _user_store[role] = {
                        "hash": get_password_hash(password),
                        "role": role
                    }
        
        if _user_store:
            return _user_store
    
    # No users configured
    raise RuntimeError(
        "No dashboard users configured. "
        "Set DASHBOARD_USERS environment variable or create secrets/dashboard_users.json"
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    # bcrypt has 72 byte limit, truncate if necessary
    password_bytes = plain_password.encode('utf-8')[:72]
    hash_bytes = hashed_password.encode('utf-8') if isinstance(hashed_password, str) else hashed_password
    return bcrypt.checkpw(password_bytes, hash_bytes)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    # bcrypt has 72 byte limit, truncate if necessary
    password_bytes = password.encode('utf-8')[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')


def create_access_token(user_id: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    settings = get_dashboard_settings()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=24)
    
    to_encode = {
        "user_id": user_id,
        "role": role,
        "exp": expire
    }
    
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm="HS256")
    return encoded_jwt


def verify_token(token: str) -> TokenData:
    """Verify JWT token and return payload."""
    settings = get_dashboard_settings()
    
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id: str = payload.get("user_id")
        role: str = payload.get("role")
        
        if user_id is None or role is None:
            raise JWTError("Invalid token payload")
        
        return TokenData(
            user_id=user_id,
            role=role,
            exp=datetime.fromtimestamp(payload.get("exp"))
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """Get current authenticated user from JWT token."""
    token_data = verify_token(credentials.credentials)
    return User(user_id=token_data.user_id, role=token_data.role)


def require_role(required_roles: list):
    """Dependency factory to require specific roles."""
    async def role_checker(user: User = Depends(get_current_user)):
        if user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return user
    return role_checker


# Predefined role dependencies
require_admin = require_role(["admin"])
require_operator = require_role(["admin", "operator"])
require_viewer = require_role(["admin", "operator", "viewer"])


async def authenticate_user(username: str, password: str) -> Optional[User]:
    """Authenticate user with username/password."""
    try:
        users = _load_users()
    except RuntimeError:
        return None
    
    user_data = users.get(username)
    if not user_data:
        return None
    
    # Verify password using bcrypt
    stored_hash = user_data.get("hash") or user_data.get("password", "")
    
    # Support both hashed and plaintext (plaintext only for migration)
    if stored_hash.startswith("$2"):
        # bcrypt hash
        if not verify_password(password, stored_hash):
            return None
    else:
        # Plaintext - should only exist in development
        import warnings
        warnings.warn(
            f"User {username} has plaintext password. Run migration to hash.",
            SecurityWarning
        )
        if stored_hash != password:
            return None
    
    return User(user_id=username, role=user_data.get("role", "viewer"))


def verify_api_key(api_key: str) -> bool:
    """Verify bot admin API key."""
    settings = get_dashboard_settings()
    return api_key == settings.bot_admin_key


class SecurityWarning(Warning):
    """Warning for security-related issues."""
    pass


def migrate_passwords():
    """
    Utility function to migrate plaintext passwords to bcrypt hashes.
    Run this once to upgrade existing user store.
    """
    try:
        users = _load_users()
    except RuntimeError:
        print("No users to migrate")
        return
    
    migrated = False
    for username, data in users.items():
        password = data.get("password")
        if password and not password.startswith("$"):
            # Plaintext password - hash it
            data["hash"] = get_password_hash(password)
            del data["password"]
            migrated = True
            print(f"Migrated password for user: {username}")
    
    if migrated:
        # Save back to file
        users_file = os.getenv("DASHBOARD_USERS_FILE", "secrets/dashboard_users.json")
        with open(users_file, 'w') as f:
            json.dump(users, f, indent=2)
        print(f"Saved migrated passwords to {users_file}")
    else:
        print("No plaintext passwords to migrate")


if __name__ == "__main__":
    # Allow running as script to migrate passwords
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        migrate_passwords()
    else:
        print("Usage: python -m src.dashboard.auth migrate")
