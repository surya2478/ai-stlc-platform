"""
Password hashing and JWT token utilities.
All secrets come from settings -- never hardcoded.

Uses bcrypt directly instead of passlib to avoid the passlib 1.7.4 / bcrypt 4.x
incompatibility (passlib raises "password cannot be longer than 72 bytes" even
for short passwords when paired with bcrypt >= 4.0).
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import uuid
import jwt
from jwt.exceptions import PyJWTError

from app.config import get_settings

settings = get_settings()

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of plain."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(
    subject: Any,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.app_secret_key, algorithm="HS256")


def create_refresh_token(
    subject: Any,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm="HS256")
