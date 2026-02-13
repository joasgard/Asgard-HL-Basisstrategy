"""Tests for internal JWT generation and verification (C6/N5)."""
import time
import pytest
import jwt as pyjwt

from shared.auth.internal_jwt import (
    generate_internal_jwt,
    verify_internal_jwt,
    TOKEN_TTL_SECONDS,
    ALGORITHM,
)


SECRET = "test-secret-for-jwt-auth"
USER_ID = "did:privy:test123"


class TestGenerateInternalJWT:

    def test_generates_valid_jwt(self):
        """Generated token decodes successfully."""
        token = generate_internal_jwt(USER_ID, SECRET)
        payload = pyjwt.decode(token, SECRET, algorithms=[ALGORITHM])
        assert payload["sub"] == USER_ID
        assert "exp" in payload
        assert "iat" in payload

    def test_default_ttl(self):
        """Token expires after TOKEN_TTL_SECONDS."""
        token = generate_internal_jwt(USER_ID, SECRET)
        payload = pyjwt.decode(token, SECRET, algorithms=[ALGORITHM])
        assert payload["exp"] - payload["iat"] == TOKEN_TTL_SECONDS

    def test_custom_ttl(self):
        """Custom TTL is respected."""
        token = generate_internal_jwt(USER_ID, SECRET, ttl=120)
        payload = pyjwt.decode(token, SECRET, algorithms=[ALGORITHM])
        assert payload["exp"] - payload["iat"] == 120


class TestVerifyInternalJWT:

    def test_verify_valid_token(self):
        """Valid token returns user_id."""
        token = generate_internal_jwt(USER_ID, SECRET)
        result = verify_internal_jwt(token, SECRET)
        assert result == USER_ID

    def test_verify_expired_token(self):
        """Expired token raises InvalidTokenError."""
        token = generate_internal_jwt(USER_ID, SECRET, ttl=-1)
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_internal_jwt(token, SECRET)

    def test_verify_wrong_secret(self):
        """Token signed with different secret is rejected."""
        token = generate_internal_jwt(USER_ID, SECRET)
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_internal_jwt(token, "wrong-secret")

    def test_verify_tampered_token(self):
        """Tampered token is rejected."""
        token = generate_internal_jwt(USER_ID, SECRET)
        # Flip a character in the payload
        parts = token.split(".")
        parts[1] = parts[1][:-1] + ("a" if parts[1][-1] != "a" else "b")
        tampered = ".".join(parts)
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_internal_jwt(tampered, SECRET)

    def test_verify_garbage_token(self):
        """Random garbage is rejected."""
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_internal_jwt("not.a.jwt", SECRET)
