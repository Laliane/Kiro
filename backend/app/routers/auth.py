"""
Authentication endpoints for LLM Consultant Advisor.

POST /auth/login   — receives Credentials, returns TokenPair
POST /auth/refresh — receives {"refresh_token": "..."}, returns new TokenPair
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.auth_service import AuthService, Credentials, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])

_auth_service = AuthService()


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenPair, status_code=status.HTTP_200_OK)
def login(credentials: Credentials) -> TokenPair:
    """Authenticate with username/password and receive a JWT token pair."""
    try:
        return _auth_service.authenticate(credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post("/refresh", response_model=TokenPair, status_code=status.HTTP_200_OK)
def refresh(body: RefreshRequest) -> TokenPair:
    """Exchange a valid refresh token for a new token pair."""
    try:
        return _auth_service.refresh(body.refresh_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
