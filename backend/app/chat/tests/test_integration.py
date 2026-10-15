import asyncio
import contextlib
import os
import socket
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from starlette.websockets import WebSocketDisconnect
from testcontainers.postgres import PostgresContainer

from app.main import app
from app.shared.db import get_db
from app.shared.models import Base, Match, Message, User
from app.shared.security import create_access_token

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_url() -> str:
    test_db_env = os.getenv("TEST_DATABASE_URL")
    if test_db_env:
        yield test_db_env
        return

    # Check if local docker-compose Postgres on port 5433 is available
    compose_test_url = (
        "postgresql+asyncpg://kpinder:kpinder@localhost:5433/kpinder_test"
    )
    try:
        sock = socket.create_connection(("localhost", 5433), timeout=1)
        sock.close()

        # Ensure kpinder_test database exists without touching the dev database
        async def _ensure_test_db() -> None:
            admin_url = "postgresql+asyncpg://kpinder:kpinder@localhost:5433/kpinder"
            admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
            async with admin_engine.connect() as conn:
                res = await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = 'kpinder_test'")
                )
                if not res.scalar():
                    await conn.execute(text("CREATE DATABASE kpinder_test"))
            await admin_engine.dispose()

        asyncio.run(_ensure_test_db())
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


@pytest.fixture
async def client(session_factory) -> AsyncGenerator[httpx.AsyncClient]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def sync_client(postgres_url: str) -> TestClient:
    engine = create_async_engine(postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def setup_conversation(session_factory):
    """Creates two matched users (Alice and Bob) and one outsider (Charlie)."""
    alice_id, bob_id, charlie_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    match_id = uuid.uuid4()

    async with session_factory() as db:
        alice = User(
            id=alice_id,
            email=f"alice_{alice_id.hex[:6]}@test.com",
            password_hash="x",
            name="Alice",
        )
        bob = User(
            id=bob_id,
            email=f"bob_{bob_id.hex[:6]}@test.com",
            password_hash="x",
            name="Bob",
        )
        charlie = User(
            id=charlie_id,
            email=f"charlie_{charlie_id.hex[:6]}@test.com",
            password_hash="x",
            name="Charlie",
        )
        db.add_all([alice, bob, charlie])
        await db.flush()
        match = Match(id=match_id, user_a_id=alice_id, user_b_id=bob_id)
        db.add(match)
        await db.commit()

    return {
        "alice_id": alice_id,
        "bob_id": bob_id,
        "charlie_id": charlie_id,
        "match_id": match_id,
        "token_alice": create_access_token(str(alice_id)),
        "token_bob": create_access_token(str(bob_id)),
        "token_charlie": create_access_token(str(charlie_id)),
    }


# --- Integration Test Cases ---


@pytest.mark.asyncio
async def test_full_rest_message_lifecycle_and_hard_delete(
    client: httpx.AsyncClient, setup_conversation, session_factory
):
    ctx = setup_conversation
    match_id = ctx["match_id"]
    headers_a = {"Authorization": f"Bearer {ctx['token_alice']}"}
    headers_b = {"Authorization": f"Bearer {ctx['token_bob']}"}

    # 1. Alice sends a message
    client_msg_id = str(uuid.uuid4())
    send_resp = await client.post(
        f"/chat/{match_id}/messages",
        json={"client_message_id": client_msg_id, "content": "Hello Bob!"},
        headers=headers_a,
    )
    assert send_resp.status_code == 201
    msg_data = send_resp.json()
    msg_id = msg_data["id"]
    assert msg_data["content"] == "Hello Bob!"

    # 2. Bob lists messages and sees Alice's message
    list_resp = await client.get(
        f"/chat/{match_id}/messages",
        headers=headers_b,
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(m["id"] == msg_id for m in items)

    # 3. Alice searches for the message
    search_resp = await client.get(
        f"/chat/{match_id}/messages/search?q=Hello",
        headers=headers_a,
    )
    assert search_resp.status_code == 200
    found = search_resp.json()
    assert len(found) == 1
    assert found[0]["id"] == msg_id

    # 4. Alice edits the message
    edit_resp = await client.patch(
        f"/chat/messages/{msg_id}",
        json={"content": "Hello Bob (edited)!"},
        headers=headers_a,
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["content"] == "Hello Bob (edited)!"

    # 5. Alice deletes the message (Hard delete per ADR-0013)
    del_resp = await client.delete(
        f"/chat/messages/{msg_id}",
        headers=headers_a,
    )
    assert del_resp.status_code == 204

    # 6. Verify row is completely removed from the real database
    async with session_factory() as db:
        deleted = (
            await db.execute(select(Message).where(Message.id == uuid.UUID(msg_id)))
        ).scalar_one_or_none()
        assert deleted is None

    # 7. Repeated delete returns 404
    repeat_del = await client.delete(
        f"/chat/messages/{msg_id}",
        headers=headers_a,
    )
    assert repeat_del.status_code == 404


@pytest.mark.asyncio
async def test_concurrent_message_dedup_unique_constraint(
    client: httpx.AsyncClient, setup_conversation, session_factory
):
    """Exercises DB UniqueConstraint('match_id', 'sender_id', 'client_message_id')
    under concurrent send attempts. Exactly one row must persist in Postgres."""
    ctx = setup_conversation
    match_id = ctx["match_id"]
    client_msg_id = str(uuid.uuid4())
    headers = {"Authorization": f"Bearer {ctx['token_alice']}"}
    payload = {"client_message_id": client_msg_id, "content": "Concurrent text"}

    async def send_call():
        return await client.post(
            f"/chat/{match_id}/messages", json=payload, headers=headers
        )

    # Fire two concurrent sends with the identical client_message_id
    resp1, resp2 = await asyncio.gather(send_call(), send_call())

    # Both requests must succeed (one created 201, one deduped 201/200)
    assert resp1.status_code in (200, 201)
    assert resp2.status_code in (200, 201)
    assert resp1.json()["id"] == resp2.json()["id"]

    # Verify real DB table has exactly 1 row for this client_message_id
    async with session_factory() as db:
        stmt = select(Message).where(
            Message.match_id == match_id,
            Message.client_message_id == uuid.UUID(client_msg_id),
        )
        rows = (await db.execute(stmt)).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_keyset_pagination_real_db(
    client: httpx.AsyncClient, setup_conversation, session_factory
):
    """Seeds 25 real database rows with staggered timestamps and verifies
    keyset pagination yields 20 items on page 1, 5 items on page 2, and no
    duplicated or skipped rows."""
    ctx = setup_conversation
    match_id = ctx["match_id"]
    alice_id = ctx["alice_id"]
    headers = {"Authorization": f"Bearer {ctx['token_alice']}"}
    base_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)

    async with session_factory() as db:
        messages = [
            Message(
                id=uuid.uuid4(),
                match_id=match_id,
                sender_id=alice_id,
                client_message_id=uuid.uuid4(),
                content=f"Message {i:02d}",
                created_at=base_time + timedelta(minutes=i),
            )
            for i in range(25)
        ]
        db.add_all(messages)
        await db.commit()

    # Fetch Page 1 (limit defaults to 20)
    page1_resp = await client.get(
        f"/chat/{match_id}/messages",
        headers=headers,
    )
    assert page1_resp.status_code == 200
    page1_data = page1_resp.json()
    assert len(page1_data["items"]) == 20
    assert page1_data["next_cursor"] is not None

    # Fetch Page 2 using cursor
    page2_resp = await client.get(
        f"/chat/{match_id}/messages?cursor={page1_data['next_cursor']}",
        headers=headers,
    )
    assert page2_resp.status_code == 200
    page2_data = page2_resp.json()
    assert len(page2_data["items"]) == 5
    assert page2_data["next_cursor"] is None

    # Verify no overlap between pages (all 25 items distinct)
    all_seen_ids = [m["id"] for m in page1_data["items"]] + [
        m["id"] for m in page2_data["items"]
    ]
    assert len(set(all_seen_ids)) == 25


@pytest.mark.asyncio
async def test_outsider_cannot_access_chat(
    client: httpx.AsyncClient, setup_conversation
):
    ctx = setup_conversation
    match_id = ctx["match_id"]
    outsider_headers = {"Authorization": f"Bearer {ctx['token_charlie']}"}

    # Charlie attempts to read conversation
    resp = await client.get(
        f"/chat/{match_id}/messages",
        headers=outsider_headers,
    )
    assert resp.status_code == 403

    # Charlie attempts to send into conversation
    resp_send = await client.post(
        f"/chat/{match_id}/messages",
        json={"client_message_id": str(uuid.uuid4()), "content": "Sneak"},
        headers=outsider_headers,
    )
    assert resp_send.status_code == 403


def test_websocket_auth_and_live_events(sync_client: TestClient, setup_conversation):
    """Verifies WebSocket live push behavior per ADR-0018:
    - Connecting without valid token closes with 1008
    - Valid connected client receives real-time events on new_message,
      message_edited, and message_deleted."""
    ctx = setup_conversation
    match_id = ctx["match_id"]
    headers_a = {"Authorization": f"Bearer {ctx['token_alice']}"}

    # 1. Anonymous connection rejected with 1008
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        sync_client.websocket_connect("/chat/ws"),
    ):
        pass
    assert exc_info.value.code == 1008

    # 2. Bob connects to WebSocket
    with sync_client.websocket_connect(f"/chat/ws?token={ctx['token_bob']}") as ws_bob:
        # Alice sends message via HTTP
        client_msg_id = str(uuid.uuid4())
        send_resp = sync_client.post(
            f"/chat/{match_id}/messages",
            json={"client_message_id": client_msg_id, "content": "Live greeting!"},
            headers=headers_a,
        )
        assert send_resp.status_code == 201
        msg_id = send_resp.json()["id"]

        # Bob receives new_message frame over WebSocket
        event_new = ws_bob.receive_json()
        assert event_new["event"] == "new_message"
        assert event_new["data"]["content"] == "Live greeting!"

        # Alice edits message via HTTP
        edit_resp = sync_client.patch(
            f"/chat/messages/{msg_id}",
            json={"content": "Live greeting edited!"},
            headers=headers_a,
        )
        assert edit_resp.status_code == 200

        # Bob receives message_edited frame
        event_edit = ws_bob.receive_json()
        assert event_edit["event"] == "message_edited"
        assert event_edit["data"]["content"] == "Live greeting edited!"

        # Alice deletes message via HTTP
        del_resp = sync_client.delete(
            f"/chat/messages/{msg_id}",
            headers=headers_a,
        )
        assert del_resp.status_code == 204

        # Bob receives message_deleted frame
        event_del = ws_bob.receive_json()
        assert event_del["event"] == "message_deleted"
        assert event_del["data"]["id"] == str(msg_id)
