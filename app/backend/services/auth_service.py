"""
Xyrox — Auth Service (Phase 3, File 6)

Real authentication logic. This is where users are created and
verified. Routes are thin wrappers over this service.

Rules:
- Usernames and emails are unique (enforced by DB + checked here).
- Passwords are hashed with bcrypt.
- Verification returns None on failure — never raises on bad creds
  (that would leak timing info).
- Every operation opens and closes its own DB session.
"""

from typing import Optional
from sqlalchemy.orm import Session

from app.backend.database.db import SessionLocal
from app.backend.models.models import User
from app.backend.security.passwords import hash_password, verify_password
from app.backend.security.tokens import create_access_token, TokenError
from app.backend.config import settings
from app.backend.tools.base import ToolValidationError


class AuthError(Exception):
    """Raised for authentication/registration failures."""
    pass


def _session() -> Session:
    return SessionLocal()


# ============================================================
# REGISTRATION
# ============================================================
def register_user(
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    timezone: str = "Africa/Lagos",
) -> User:
    """
    Create a new user. Raises AuthError if the username or email
    is already taken or if the password is invalid.
    """
    username = username.strip().lower()
    email = email.strip().lower()

    if not username or not email or not password:
        raise AuthError("username, email, and password are required.")

    db = _session()
    try:
        if db.query(User).filter_by(username=username).first():
            raise AuthError(f"Username '{username}' is already taken.")
        if db.query(User).filter_by(email=email).first():
            raise AuthError(f"Email '{email}' is already registered.")

        try:
            hashed = hash_password(password)
        except ToolValidationError as exc:
            raise AuthError(str(exc)) from exc

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=hashed,
            timezone=timezone,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


# ============================================================
# LOGIN
# ============================================================
def authenticate(username: str, password: str) -> Optional[User]:
    """
    Return the User if credentials are valid, else None.
    Does NOT raise on bad credentials — the route decides the response.
    """
    if not username or not password:
        return None

    db = _session()
    try:
        user = db.query(User).filter_by(username=username.strip().lower()).first()
        if user is None:
            # Do a dummy hash to reduce timing side-channel
            verify_password(password, "$2b$12$" + "x" * 53)
            return None
        if not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user
    finally:
        db.close()


# ============================================================
# TOKEN ISSUANCE
# ============================================================
def issue_token_for(user: User) -> dict:
    """
    Return a dict matching schemas.TokenResponse:
        {"access_token": ..., "token_type": "bearer", "expires_in": N}
    """
    minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES or 30
    token = create_access_token(subject=user.username, expires_minutes=minutes)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": minutes * 60,
    }


def get_user_by_username(username: str) -> Optional[User]:
    """
    Fetch a user by username. Used by the /me route after token verification.
    """
    if not username:
        return None
    db = _session()
    try:
        return db.query(User).filter_by(username=username.strip().lower()).first()
    finally:
        db.close()