"""
Xyrox — Auth Schemas (Phase 3, File 5)

Pydantic models for authentication API requests and responses.

Rules:
- Passwords are never in any response model.
- Usernames and emails are validated at the schema level too.
- Extra fields are forbidden — no accidental data leakage.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    full_name: Optional[str] = Field(default=None, max_length=128)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    """A user as exposed by the API. NEVER contains hashed_password."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    is_active: bool
    timezone: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class LoginResponse(BaseModel):
    user: UserPublic
    token: TokenResponse