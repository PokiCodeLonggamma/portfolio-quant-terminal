"""JWT auth helpers + FastAPI ``require_auth`` dependency.

Single-user model: credentials are read from env vars:
- ``QT_ADMIN_EMAIL`` — the only allowed login email
- ``QT_ADMIN_PASSWORD_HASH`` — bcrypt hash (generate via scripts/hash_password.py)
- ``JWT_SECRET`` — HS256 secret (random 32-byte string, generate any way)
- ``QT_AUTH_COOKIE_DOMAIN`` — optional, set in prod ("" in dev)
- ``QT_AUTH_TOKEN_TTL_SECONDS`` — optional, default 86400 (24h)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Cookie, HTTPException, status
from jose import JWTError, jwt

COOKIE_NAME = "qt_auth"
JWT_ALG = "HS256"
BCRYPT_MAX_BYTES = 72  # bcrypt spec limit


def _bcrypt_safe(password: str) -> bytes:
    """bcrypt rejects >72 bytes — truncate to keep the call safe."""
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]


def _settings() -> dict:
    return {
        "email": os.getenv("QT_ADMIN_EMAIL", ""),
        "pwd_hash": os.getenv("QT_ADMIN_PASSWORD_HASH", ""),
        "secret": os.getenv("JWT_SECRET", "dev-only-secret-change-me"),
        "cookie_domain": os.getenv("QT_AUTH_COOKIE_DOMAIN", "") or None,
        "ttl_s": int(os.getenv("QT_AUTH_TOKEN_TTL_SECONDS", "86400")),
    }


def verify_credentials(email: str, password: str) -> bool:
    """Constant-time-ish credential check against the env-stored hash."""
    s = _settings()
    if not s["email"] or not s["pwd_hash"]:
        # If env not set, auth is effectively disabled — refuse everything.
        return False
    if email.strip().lower() != s["email"].strip().lower():
        return False
    try:
        return bcrypt.checkpw(_bcrypt_safe(password), s["pwd_hash"].encode("utf-8"))
    except Exception:
        return False


def issue_jwt(email: str) -> tuple[str, datetime]:
    """Encode a JWT for ``email`` with the default TTL. Returns (token, exp)."""
    s = _settings()
    exp = datetime.now(timezone.utc) + timedelta(seconds=s["ttl_s"])
    payload = {
        "sub": email,
        "exp": int(exp.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    token = jwt.encode(payload, s["secret"], algorithm=JWT_ALG)
    return token, exp


def decode_jwt(token: str) -> dict[str, Any]:
    """Decode + validate ``token``. Raises 401 on any error."""
    s = _settings()
    try:
        payload = jwt.decode(token, s["secret"], algorithms=[JWT_ALG])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid auth token: {exc}",
        )
    return payload


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
def require_auth(qt_auth: str | None = Cookie(default=None, alias=COOKIE_NAME)) -> dict[str, Any]:
    """Read the ``qt_auth`` cookie, validate the JWT, return the payload.

    Raises 401 if missing or invalid.

    Usage::

        @router.get("/...")
        async def handler(user: dict = Depends(require_auth)):
            ...
    """
    if not qt_auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated (missing cookie)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_jwt(qt_auth)


# ---------------------------------------------------------------------------
# Cookie helpers — used by the routes
# ---------------------------------------------------------------------------
def build_auth_cookie_kwargs(token: str) -> dict:
    """kwargs for ``Response.set_cookie`` matching our security policy."""
    s = _settings()
    return {
        "key": COOKIE_NAME,
        "value": token,
        "max_age": s["ttl_s"],
        "expires": s["ttl_s"],
        "httponly": True,
        "samesite": "lax",
        "secure": s["cookie_domain"] is not None,  # secure only when domain explicitly set
        "domain": s["cookie_domain"],
        "path": "/",
    }


def build_clear_cookie_kwargs() -> dict:
    s = _settings()
    return {
        "key": COOKIE_NAME,
        "value": "",
        "max_age": 0,
        "expires": 0,
        "httponly": True,
        "samesite": "lax",
        "secure": s["cookie_domain"] is not None,
        "domain": s["cookie_domain"],
        "path": "/",
    }
