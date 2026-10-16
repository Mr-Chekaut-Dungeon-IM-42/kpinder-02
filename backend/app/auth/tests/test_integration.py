import asyncio
import uuid

import pytest

from app.auth.commands import SignupCommand
from app.auth.schemas import SignupRequest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_concurrent_signup_same_email_only_one_succeeds(session_factory):
    unique = uuid.uuid4().hex[:6]
    data = SignupRequest(
        email=f"race_{unique}@b.com", password="password123", name="Racer"
    )

    async def attempt():
        async with session_factory() as db:
            try:
                await SignupCommand(db=db).execute(data)
                return "ok"
            except Exception as exc:  # noqa: BLE001
                status_code = getattr(exc, "status_code", None)
                return status_code

    results = await asyncio.gather(attempt(), attempt())

    assert results.count("ok") == 1
    assert results.count(409) == 1
