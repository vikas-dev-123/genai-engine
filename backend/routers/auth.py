"""Authentication API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_user, get_db
from models.user import User
from schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse
from services.auth_service import (
    create_access_token,
    create_refresh_token,
    create_user,
    decode_token,
    get_user_by_email,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Register a new account and return tokens."""
    existing = await get_user_by_email(body.email, db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    user = await create_user(body, db)
    uid = str(user.id)
    access = create_access_token(uid)
    refresh = create_refresh_token(uid)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate and return tokens."""
    user = await get_user_by_email(body.email, db)
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    uid = str(user.id)
    return TokenResponse(
        access_token=create_access_token(uid),
        refresh_token=create_refresh_token(uid),
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh")
async def refresh_session(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Issue a new access token from a valid refresh token for an active user."""
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
    )
    try:
        payload = decode_token(body.refresh_token)
    except HTTPException:
        raise invalid from None
    if payload.get("type") != "refresh":
        raise invalid
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except ValueError:
        raise invalid from None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise invalid
    access = create_access_token(str(user.id))
    return {"access_token": access, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def me(current: User = Depends(get_current_user)) -> UserResponse:
    """Return the authenticated user profile."""
    return UserResponse.model_validate(current)
