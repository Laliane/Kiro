"""
FastAPI dependencies for LLM Consultant Advisor.

get_current_consultant — extracts and validates the JWT from the
    Authorization: Bearer <token> header, returning ConsultantIdentity.
    Raises HTTP 401 for missing or invalid tokens.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth_service import AuthService, ConsultantIdentity

_bearer_scheme = HTTPBearer(auto_error=False)
_auth_service = AuthService()


def get_current_consultant(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> ConsultantIdentity:
    """
    FastAPI dependency that validates the Bearer JWT and returns the
    ConsultantIdentity. Raises HTTP 401 if the token is absent or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return _auth_service.validate_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
