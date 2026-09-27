"""Registration, login, token types and refresh."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import update

from db.session import AsyncSessionLocal
from models.user import User
from tests.conftest import register


async def test_register_returns_tokens_and_user(client: AsyncClient) -> None:
    body = await register(client)
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email"] == "ada@example.com"
    assert "hashed_password" not in body["user"]


async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    await register(client)
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": "another-password", "name": "Ada"},
    )
    assert resp.status_code == 400


async def test_register_validates_password_length(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "short", "name": "Bob"},
    )
    assert resp.status_code == 422


async def test_login_success_and_wrong_password(client: AsyncClient) -> None:
    await register(client)
    ok = await client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "correct-horse-battery"},
    )
    assert ok.status_code == 200
    bad = await client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "wrong-password"},
    )
    assert bad.status_code == 401


async def test_long_passwords_are_not_truncated_to_the_same_hash(client: AsyncClient) -> None:
    # bcrypt alone only reads 72 bytes; two passwords differing after byte 72 must not collide.
    prefix = "x" * 80
    await client.post(
        "/api/v1/auth/register",
        json={"email": "long@example.com", "password": prefix + "A", "name": "Long"},
    )
    ok = await client.post(
        "/api/v1/auth/login", json={"email": "long@example.com", "password": prefix + "A"}
    )
    assert ok.status_code == 200
    collision = await client.post(
        "/api/v1/auth/login", json={"email": "long@example.com", "password": prefix + "B"}
    )
    assert collision.status_code == 401


def test_legacy_truncated_hashes_still_verify() -> None:
    from services.auth_service import _legacy_truncate, pwd_context, verify_password

    long_password = "y" * 100
    legacy_hash = pwd_context.hash(_legacy_truncate(long_password))
    assert verify_password(long_password, legacy_hash)
    assert not verify_password("y" * 50, legacy_hash)


async def test_me_requires_access_token(client: AsyncClient) -> None:
    tokens = await register(client)
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["name"] == "Ada"


async def test_refresh_token_cannot_be_used_as_access_token(client: AsyncClient) -> None:
    tokens = await register(client)
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert resp.status_code == 401


async def test_refresh_issues_new_access_token(client: AsyncClient) -> None:
    tokens = await register(client)
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    new_access = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


async def test_refresh_rejects_access_token_and_garbage(client: AsyncClient) -> None:
    tokens = await register(client)
    for bad in (tokens["access_token"], "not-a-jwt"):
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": bad})
        assert resp.status_code == 401


async def test_refresh_rejected_for_deactivated_user(client: AsyncClient) -> None:
    tokens = await register(client)
    async with AsyncSessionLocal() as db:
        await db.execute(update(User).values(is_active=False))
        await db.commit()
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401
