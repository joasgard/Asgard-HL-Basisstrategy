"""
Internal JWT utilities for dashboard ↔ bot communication.

The dashboard generates short-lived JWTs signed with server_secret (HS256)
containing the authenticated user_id. The bot verifies the JWT and extracts
the user_id, preventing header spoofing (N5/C6).

Tokens are short-lived (60s) because they're used for immediate API calls,
not session management.
"""
import time
from typing import Optional

import jwt

# Token lifetime — short since these are for immediate API calls
TOKEN_TTL_SECONDS = 60

# Algorithm — HS256 is sufficient for symmetric server-to-server auth
ALGORITHM = "HS256"


def generate_internal_jwt(
    user_id: str,
    secret: str,
    ttl: int = TOKEN_TTL_SECONDS,
) -> str:
    """Generate a short-lived JWT for internal API calls.

    Args:
        user_id: Privy user ID to embed in token.
        secret: Shared secret (server_secret.txt).
        ttl: Token lifetime in seconds.

    Returns:
        Encoded JWT string.
    """
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_internal_jwt(
    token: str,
    secret: str,
) -> Optional[str]:
    """Verify an internal JWT and extract user_id.

    Args:
        token: JWT string.
        secret: Shared secret (server_secret.txt).

    Returns:
        user_id if valid, None if expired or invalid.

    Raises:
        jwt.InvalidTokenError: On any JWT validation failure.
    """
    payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    return payload.get("sub")
