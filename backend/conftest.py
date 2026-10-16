import asyncio
import contextlib
import os
import socket

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from app.shared.models import Base


async def ensure_test_database(
    test_host: str,
    test_port: int,
    test_db: str = "kpinder_test",
    admin_db: str = "kpinder",
    user: str = "kpinder",
    password: str = "kpinder",
) -> None:
    """Ensure that the test database exists on the running postgres instance."""
    admin_url = (
        f"postgresql+asyncpg://{user}:{password}@{test_host}:{test_port}/{admin_db}"
    )
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        res = await conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{test_db}'")
        )
        if not res.scalar():
            await conn.execute(text(f"CREATE DATABASE {test_db}"))
    await admin_engine.dispose()


@pytest.fixture(scope="module")
def postgres_url() -> str:
    test_db_env = os.getenv("TEST_DATABASE_URL")
    if test_db_env:
        yield test_db_env
        return

    test_host = os.getenv("TEST_DB_HOST", os.getenv("DB_HOST", "localhost"))
    test_port = int(os.getenv("TEST_DB_PORT", "5432"))
    compose_test_url = (
        f"postgresql+asyncpg://kpinder:kpinder@{test_host}:{test_port}/kpinder_test"
    )
    try:
        sock = socket.create_connection((test_host, test_port), timeout=1)
        sock.close()

        asyncio.run(ensure_test_database(test_host, test_port))
        yield compose_test_url
        return
    except OSError:
        pass

    # Fallback to testcontainers
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
