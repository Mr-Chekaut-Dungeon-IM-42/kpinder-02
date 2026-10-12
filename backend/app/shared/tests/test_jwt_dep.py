import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.shared.config import settings
from app.shared.jwt_dep import get_current_user_id
from app.shared.security import create_access_token


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_valid_token_returns_user_id():
    user_id = uuid.uuid4()
    token = create_access_token(subject=str(user_id))
    assert get_current_user_id(_creds(token)) == user_id


def test_garbage_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(_creds("not-a-jwt"))
    assert exc_info.value.status_code == 401


def test_token_with_non_uuid_subject_raises_401():
    token = create_access_token(subject="not-a-uuid")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(_creds(token))
    assert exc_info.value.status_code == 401


def test_expired_token_raises_401():
    expired = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(_creds(expired))
    assert exc_info.value.status_code == 401
