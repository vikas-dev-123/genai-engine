"""FastAPI dependencies."""

from collections.abc import AsyncGenerator
from typing import Any
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import AsyncSessionLocal
from models.user import User
from redis_client import get_shared_redis
from services.auth_service import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a request-scoped async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_redis():
    """Return the shared Redis (or fake Redis) client."""
    return await get_shared_redis()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the current user from a Bearer JWT."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload: dict[str, Any] = decode_token(token)
    if payload.get("type") != "access":
        raise credentials_exc
    sub = payload.get("sub")
    if sub is None:
        raise credentials_exc
    try:
        user_id = uuid.UUID(str(sub))
    except ValueError as exc:
        raise credentials_exc from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exc
    return user
