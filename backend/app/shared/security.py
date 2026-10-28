from datetime import UTC, datetime, timedelta

import anyio
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.shared.config import settings

_hasher = PasswordHasher()


async def hash_password(password: str) -> str:
    # Argon2 is deliberately CPU-expensive — run_sync offloads it to a
    # worker thread instead of blocking the single event loop for the
    # duration of every hash, which under concurrent signup/login load
    # otherwise serializes the entire process, not just this request
    # (ai/audit/lab-5.md Part B.1 — removing this one call from the hot
    # path during a 150-concurrent load test roughly doubled throughput).
    return await anyio.to_thread.run_sync(_hasher.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    try:
        return await anyio.to_thread.run_sync(_hasher.verify, password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return payload["sub"]
