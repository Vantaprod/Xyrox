"""
Xyrox — Auth Routes (Phase 3)

HTTP endpoints for user registration, login, and identity check.

Routes:
    POST /api/v1/auth/register → create user, return UserPublic
    POST /api/v1/auth/login    → return token + user
    GET  /api/v1/auth/me       → return current user

Rules:
- Passwords never appear in any response.
- Registration errors that leak existence (username taken) use 400,
  not 200, and are explicit.
- Login failures are always 401 with a generic message — never
  distinguish between "user not found" and "wrong password".
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.backend.api.deps import get_current_user
from app.backend.models.models import User
from app.backend.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    LoginResponse,
    TokenResponse,
    UserPublic,
)
from app.backend.services.auth_service import (
    AuthError,
    register_user,
    authenticate,
    issue_token_for,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest) -> UserPublic:
    """
    Create a new user account. Returns the public user shape.
    Never returns the password or hash.
    """
    try:
        user = register_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return UserPublic.model_validate(user)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """
    Verify credentials and return a signed JWT.
    """
    user = authenticate(payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = issue_token_for(user)

    return LoginResponse(
        user=UserPublic.model_validate(user),
        token=TokenResponse(**token_data),
    )


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    """
    Return the authenticated user. Requires a valid Bearer token.
    """
    return UserPublic.model_validate(current_user)