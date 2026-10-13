import asyncio
import contextlib
import os
import socket
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.auth import service
from app.auth.schemas import SignupRequest
from app.shared.models import Base

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_url():
    test_db_env = os.getenv("TEST_DATABASE_URL")
    if test_db_env:
        yield test_db_env
        return

    compose_test_url = (
        "postgresql+asyncpg://kpinder:kpinder@localhost:5433/kpinder_test"
    )
    try:
        sock = socket.create_connection(("localhost", 5433), timeout=1)
        sock.close()
        yield compose_test_url
        return
    except OSError:
        pass

    container = PostgresContainer("postgis/postgis:16-3.4")
    try:
        container.start()
        yield container.get_connection_url().replace(
            "postgresql+psycopg2", "postgresql+asyncpg"
        )
    finally:
        with contextlib.suppress(Exception):
            container.stop()


@pytest.fixture
async def session_factory(postgres_url: str):
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_signup_same_email_only_one_succeeds(session_factory):
    unique = uuid.uuid4().hex[:6]
    data = SignupRequest(
        email=f"race_{unique}@b.com", password="password123", name="Racer"
    )

    async def attempt():
        async with session_factory() as db:
            try:
                await service.signup(db, data)
                return "ok"
            except Exception as exc:  # noqa: BLE001
                status_code = getattr(exc, "status_code", None)
                return status_code

    results = await asyncio.gather(attempt(), attempt())

    assert results.count("ok") == 1
    assert results.count(409) == 1
