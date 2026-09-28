"""
Xyrox — JWT Tokens (Phase 3, File 3)

Issues and verifies signed JSON Web Tokens for authentication.

Rules:
- Tokens are signed with settings.SECRET_KEY using HS256.
- Payload contains: sub (username), exp (expiry), iat, type.
- verify_token() returns the payload dict, or raises TokenError.
- Expired, malformed, or wrong-signature tokens are all rejected.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError

from app.backend.config import settings


class TokenError(Exception):
    """Raised when a token is invalid, expired, or malformed."""
    pass


ALGORITHM = settings.ALGORITHM or "HS256"


def create_access_token(
    subject: str,
    expires_minutes: Optional[int] = None,
) -> str:
    """
    Create a signed JWT for the given subject (username).

    Returns the encoded token string.
    """
    if not isinstance(subject, str) or not subject.strip():
        raise TokenError("Token subject must be a non-empty string.")

    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES or 30
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str) -> dict:
    """
    Verify a token and return its payload. Raises TokenError on any problem.
    """
    if not isinstance(token, str) or not token.strip():
        raise TokenError("Token is empty.")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise TokenError(f"Invalid token: {exc}") from exc

    if payload.get("type") != "access":
        raise TokenError("Token is not an access token.")

    subject = payload.get("sub")
    if not subject:
        raise TokenError("Token has no subject.")

    return payload