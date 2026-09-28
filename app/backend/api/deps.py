"""
Xyrox — API Dependencies (Phase 3)

Shared FastAPI dependencies. The most important is get_current_user,
which is the authentication gate for all protected routes.

Rules:
- Every protected route MUST use this dependency.
- Missing, malformed, expired, or wrong-signature tokens → 401.
- Deactivated users → 401.
- No dependency ever trusts a request body for identity. Identity
  comes only from a verified JWT.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.backend.models.models import User
from app.backend.security.tokens import verify_access_token, TokenError
from app.backend.services.auth_service import get_user_by_username


# auto_error=False so we can return 401 with a proper WWW-Authenticate
# header instead of the default 403.
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> User:
    """
    Resolve the current authenticated user from the Bearer token.
    Raises HTTPException(401) on any failure.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = verify_access_token(token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has no subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_username(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user