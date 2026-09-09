import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from jwt import ExpiredSignatureError, PyJWTError

from app.auth.exceptions import TokenExpired, TokenInvalid
from app.infra.config import settings

"""
- create access JWT tokens.
- verify access token and refresh token types.
- decode JWT tokens.
"""

def create_token(
    *,
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict | None = None,
) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_access_token(user_id: uuid.UUID, roles: list[str] | None = None) -> str:
    return create_token(
        subject=str(user_id),
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={"roles": roles or []},
    )


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except ExpiredSignatureError:
        raise TokenExpired("expired token")
    except PyJWTError:
        raise TokenInvalid("invalid token")


def verify_access_token(token: str) -> dict:
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise TokenInvalid("incorrect token")

    return payload

def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)

