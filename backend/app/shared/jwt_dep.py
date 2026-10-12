import uuid

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.shared.security import decode_access_token

_bearer = HTTPBearer()


def _parse_and_validate_token(token: str) -> uuid.UUID:
    try:
        subject = decode_access_token(token)
        return uuid.UUID(subject)
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> uuid.UUID:
    return _parse_and_validate_token(credentials.credentials)


def get_current_user_id_ws(token: str | None = Query(default=None)) -> uuid.UUID:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing auth token",
        )
    return _parse_and_validate_token(token)
