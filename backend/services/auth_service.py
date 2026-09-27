"""Authentication helpers: password hashing and JWT tokens."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.user import User
from schemas.auth import RegisterRequest

pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    """Hash a plaintext password.

    bcrypt_sha256 pre-hashes with SHA-256, so the full password counts
    (plain bcrypt silently ignores everything after 72 bytes).
    """
    return pwd_context.hash(password)


def _legacy_truncate(password: str) -> str:
    """Earlier releases cut passwords to 72 UTF-8 bytes before hashing."""
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored hash."""
    if pwd_context.verify(plain, hashed):
        return True
    # Accounts created by earlier releases with passwords over 72 bytes were
    # hashed from the truncated form; keep them able to log in.
    truncated = _legacy_truncate(plain)
    return truncated != plain and pwd_context.verify(truncated, hashed)


def create_access_token(user_id: str) -> str:
    """Create a short-lived access JWT."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": user_id,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh JWT."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
    )
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT or raise 401."""
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc


async def get_user_by_email(email: str, db: AsyncSession) -> User | None:
    """Fetch a user by email address."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(data: RegisterRequest, db: AsyncSession) -> User:
    """Persist a new user with hashed password."""
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        name=data.name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
