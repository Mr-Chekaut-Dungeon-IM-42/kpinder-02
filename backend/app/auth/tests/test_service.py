import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.auth import service
from app.auth.models import User
from app.auth.schemas import LoginRequest, SignupRequest
from app.shared.security import hash_password


@pytest.mark.asyncio
async def test_signup_success():
    db = AsyncMock()
    created = User(id=uuid.uuid4(), email="a@b.com", password_hash="x", name="Alice")
    with patch("app.auth.service.repository.create_user", return_value=created):
        user = await service.signup(
            db, SignupRequest(email="a@b.com", password="password123", name="Alice")
        )
    assert user.email == "a@b.com"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_signup_duplicate_email_raises_409():
    db = AsyncMock()
    with (
        patch(
            "app.auth.service.repository.create_user",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.signup(
            db, SignupRequest(email="a@b.com", password="password123", name="Alice")
        )
    assert exc_info.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_success():
    db = AsyncMock()
    user = User(
        id=uuid.uuid4(),
        email="a@b.com",
        password_hash=hash_password("password123"),
        name="Alice",
    )
    with patch("app.auth.service.repository.get_user_by_email", return_value=user):
        token = await service.login(
            db, LoginRequest(email="a@b.com", password="password123")
        )
    assert token.token_type == "bearer"
    assert token.access_token


@pytest.mark.asyncio
async def test_login_wrong_password_raises_401():
    db = AsyncMock()
    user = User(
        id=uuid.uuid4(),
        email="a@b.com",
        password_hash=hash_password("password123"),
        name="Alice",
    )
    with (
        patch("app.auth.service.repository.get_user_by_email", return_value=user),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.login(db, LoginRequest(email="a@b.com", password="wrong"))
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_raises_401():
    db = AsyncMock()
    with (
        patch("app.auth.service.repository.get_user_by_email", return_value=None),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.login(
            db, LoginRequest(email="nobody@b.com", password="password123")
        )
    assert exc_info.value.status_code == 401
