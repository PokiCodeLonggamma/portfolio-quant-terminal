"""Auth endpoints — single-user JWT login + me + logout.

POST /api/auth/login   { email, password }  → set HttpOnly cookie
GET  /api/auth/me                            → { email, exp }
POST /api/auth/logout                        → clear cookie
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr

from api.auth import (
    build_auth_cookie_kwargs,
    build_clear_cookie_kwargs,
    issue_jwt,
    require_auth,
    verify_credentials,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    ok: bool
    email: str
    exp: datetime


class MeResponse(BaseModel):
    email: str
    exp: datetime


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response) -> LoginResponse:
    if not verify_credentials(payload.email, payload.password):
        # Same error message regardless of which field was wrong
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token, exp = issue_jwt(payload.email)
    response.set_cookie(**build_auth_cookie_kwargs(token))
    return LoginResponse(ok=True, email=payload.email, exp=exp)


@router.get("/me", response_model=MeResponse)
async def me(user: dict[str, Any] = Depends(require_auth)) -> MeResponse:
    return MeResponse(
        email=user.get("sub", ""),
        exp=datetime.fromtimestamp(int(user.get("exp", 0)), tz=timezone.utc),
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.set_cookie(**build_clear_cookie_kwargs())
    return {"ok": True}
