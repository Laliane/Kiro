"""
Auth Service for LLM Consultant Advisor.

Handles JWT-based authentication, token validation, refresh, and session
expiration by inactivity.

Environment variables:
  JWT_SECRET  Secret key used to sign JWT tokens (required)

For MVP, users are stored in memory. No database dependency.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Literal

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from app.database import sessions_store

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_JWT_SECRET: str = os.environ.get("JWT_SECRET", "change-me-in-production")
_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = 30
_REFRESH_TOKEN_EXPIRE_DAYS = 7
_SESSION_INACTIVITY_MINUTES = 30

# ---------------------------------------------------------------------------
# Password hashing — using bcrypt directly (passlib incompatible with bcrypt 4.x)
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password[:72].encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(plain[:72].encode(), hashed.encode())


# ---------------------------------------------------------------------------
# In-memory user store (MVP — replace with DB in production)
# ---------------------------------------------------------------------------

# { username: hashed_password }
_USERS: dict[str, str] = {
    "consultant": _hash_password("password123"),
    "admin": _hash_password("admin123"),
}

# { username: consultant_id }
_USER_IDS: dict[str, str] = {
    "consultant": "consultant-001",
    "admin": "admin-001",
}

# ---------------------------------------------------------------------------
# Auxiliary models
# ---------------------------------------------------------------------------


class Credentials(BaseModel):
    username: str
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class ConsultantIdentity(BaseModel):
    consultant_id: str
    username: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _create_token(
    data: dict,
    expires_delta: timedelta,
    token_type: str,
) -> str:
    """Create a signed JWT with an expiry claim."""
    payload = dict(data)
    payload["type"] = token_type
    payload["exp"] = datetime.now(tz=timezone.utc) + expires_delta
    return jwt.encode(payload, _JWT_SECRET, algorithm=_ALGORITHM)


def _decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises JWTError on failure."""
    return jwt.decode(token, _JWT_SECRET, algorithms=[_ALGORITHM])


# ---------------------------------------------------------------------------
# AuthService
# ---------------------------------------------------------------------------


class AuthService:
    """Handles authentication, token validation and refresh."""

    def authenticate(self, credentials: Credentials) -> TokenPair:
        """
        Validate credentials and return a TokenPair.

        Raises ValueError if credentials are invalid.
        """
        hashed = _USERS.get(credentials.username)
        if hashed is None or not _verify_password(credentials.password, hashed):
            raise ValueError("Invalid username or password")

        consultant_id = _USER_IDS[credentials.username]
        payload = {"sub": credentials.username, "consultant_id": consultant_id}

        access_token = _create_token(
            payload,
            timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES),
            token_type="access",
        )
        refresh_token = _create_token(
            payload,
            timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS),
            token_type="refresh",
        )
        return TokenPair(access_token=access_token, refresh_token=refresh_token)

    def validate_token(self, token: str) -> ConsultantIdentity:
        """
        Validate an access token and return the ConsultantIdentity.

        Raises ValueError for invalid, expired, or wrong-type tokens.
        """
        try:
            payload = _decode_token(token)
        except JWTError as exc:
            raise ValueError("Invalid or expired token") from exc

        if payload.get("type") != "access":
            raise ValueError("Token is not an access token")

        username: str | None = payload.get("sub")
        consultant_id: str | None = payload.get("consultant_id")
        if not username or not consultant_id:
            raise ValueError("Token payload is missing required fields")

        return ConsultantIdentity(consultant_id=consultant_id, username=username)

    def refresh(self, refresh_token: str) -> TokenPair:
        """
        Issue a new TokenPair from a valid refresh token.

        Raises ValueError for invalid, expired, or wrong-type tokens.
        """
        try:
            payload = _decode_token(refresh_token)
        except JWTError as exc:
            raise ValueError("Invalid or expired refresh token") from exc

        if payload.get("type") != "refresh":
            raise ValueError("Token is not a refresh token")

        username: str | None = payload.get("sub")
        consultant_id: str | None = payload.get("consultant_id")
        if not username or not consultant_id:
            raise ValueError("Refresh token payload is missing required fields")

        new_payload = {"sub": username, "consultant_id": consultant_id}
        access_token = _create_token(
            new_payload,
            timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES),
            token_type="access",
        )
        new_refresh_token = _create_token(
            new_payload,
            timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS),
            token_type="refresh",
        )
        return TokenPair(access_token=access_token, refresh_token=new_refresh_token)


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class SessionManager:
    """Manages session lifecycle, including inactivity-based expiration."""

    def check_and_expire_sessions(self) -> list[str]:
        """
        Iterate over sessions_store and mark as 'expired' any session whose
        last_activity_at is more than SESSION_INACTIVITY_MINUTES ago.

        Returns the list of session IDs that were expired in this call.
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(
            minutes=_SESSION_INACTIVITY_MINUTES
        )
        expired_ids: list[str] = []

        for session_id, session in sessions_store.items():
            if session.status != "active":
                continue

            last_activity = session.last_activity_at
            # Normalise to UTC-aware if naive
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)

            if last_activity < cutoff:
                session.status = "expired"
                expired_ids.append(session_id)

        return expired_ids
