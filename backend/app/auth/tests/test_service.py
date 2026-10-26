import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.auth.commands import LoginCommand, SignupCommand
from app.auth.schemas import LoginRequest, SignupRequest
from app.shared.models import User
from app.shared.security import decode_access_token, hash_password


@pytest.mark.asyncio
async def test_signup_success():
    db = AsyncMock()
    created = User(id=uuid.uuid4(), email="a@b.com", password_hash="x", name="Alice")
    with patch("app.auth.commands.repository.create_user", return_value=created):
        cmd = SignupCommand(db=db)
        user = await cmd.execute(
            SignupRequest(email="a@b.com", password="password123", name="Alice")
        )
    assert user.email == "a@b.com"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_signup_duplicate_email_raises_409():
    db = AsyncMock()
    with (
        patch(
            "app.auth.commands.repository.create_user",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        cmd = SignupCommand(db=db)
        await cmd.execute(
            SignupRequest(email="a@b.com", password="password123", name="Alice")
        )
    assert exc_info.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_success():
    db = AsyncMock()
    user = User(
        id=uuid.uuid4(),
        email="a@b.com",
        password_hash=await hash_password("password123"),
        name="Alice",
    )
    with patch("app.auth.commands.repository.get_user_by_email", return_value=user):
        cmd = LoginCommand(db=db)
        token = await cmd.execute(LoginRequest(email="a@b.com", password="password123"))
    assert token.token_type == "bearer"
    assert token.access_token
    assert decode_access_token(token.access_token) == str(user.id)


@pytest.mark.asyncio
async def test_login_wrong_password_raises_401():
    db = AsyncMock()
    user = User(
        id=uuid.uuid4(),
        email="a@b.com",
        password_hash=await hash_password("password123"),
        name="Alice",
    )
    with (
        patch("app.auth.commands.repository.get_user_by_email", return_value=user),
        pytest.raises(HTTPException) as exc_info,
    ):
        cmd = LoginCommand(db=db)
        await cmd.execute(LoginRequest(email="a@b.com", password="wrong"))
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_raises_401():
    db = AsyncMock()
    with (
        patch("app.auth.commands.repository.get_user_by_email", return_value=None),
        pytest.raises(HTTPException) as exc_info,
    ):
        cmd = LoginCommand(db=db)
        await cmd.execute(LoginRequest(email="nobody@b.com", password="password123"))
    assert exc_info.value.status_code == 401
