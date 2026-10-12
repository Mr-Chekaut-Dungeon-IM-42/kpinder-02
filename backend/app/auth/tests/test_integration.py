import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.auth import service
from app.auth.schemas import SignupRequest
from app.shared.models import Base

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("postgis/postgis:16-3.4") as container:
        yield container


@pytest.fixture
async def session_factory(postgres_container):
    url = postgres_container.get_connection_url().replace(
        "postgresql+psycopg2", "postgresql+asyncpg"
    )
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_signup_same_email_only_one_succeeds(session_factory):
    data = SignupRequest(email="race@b.com", password="password123", name="Racer")

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
