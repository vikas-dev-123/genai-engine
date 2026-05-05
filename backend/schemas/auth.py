"""Authentication Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """User registration payload."""

    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=2)


class LoginRequest(BaseModel):
    """Login payload."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Public user representation."""

    id: UUID
    email: str
    name: str
    timezone: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """OAuth-style token pair with user."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshRequest(BaseModel):
    """Refresh token request body."""

    refresh_token: str
