import asyncio
import json
import os
import uuid

import httpx
import pytest
import websockets

pytestmark = pytest.mark.e2e

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
WS_URL = os.getenv(
    "E2E_WS_URL",
    BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/chat/ws",
)


@pytest.fixture(scope="module")
async def ensure_server_is_running():
    """Verifies that the black-box backend server is running before tests."""
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=2.0) as client:
            resp = await client.get("/health")
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                return
    except Exception as exc:
        pytest.skip(
            f"E2E server is not reachable at {BASE_URL} ({exc}). "
            "Please start the backend server to run E2E tests."
        )


@pytest.mark.asyncio
async def test_full_cross_slice_user_journey(ensure_server_is_running):
    """Executes a complete black-box user journey across all slices:
    1. Auth: Sign up and log in Alice & Bob over public HTTP.
    2. Profile: Update profiles (age, bio, preferences).
    3. Matching: Alice & Bob like each other -> mutual match is created.
    4. Chat + WebSockets: Bob establishes a real TCP WebSocket connection.
       Alice sends, edits, and deletes messages via HTTP REST.
       Bob receives real-time push event frames over the live WebSocket.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as http:
        # --- 1. Signup & Login ---
        unique_a = uuid.uuid4().hex[:6]
        unique_b = uuid.uuid4().hex[:6]
        email_a = f"alice_{unique_a}@example.com"
        email_b = f"bob_{unique_b}@example.com"
        password = "strongpassword123"

        # Sign up Alice
        resp_signup_a = await http.post(
            "/auth/signup",
            json={"email": email_a, "password": password, "name": "Alice"},
        )
        assert resp_signup_a.status_code == 201, resp_signup_a.text
        alice_id = resp_signup_a.json()["id"]

        # Sign up Bob
        resp_signup_b = await http.post(
            "/auth/signup",
            json={"email": email_b, "password": password, "name": "Bob"},
        )
        assert resp_signup_b.status_code == 201, resp_signup_b.text
        bob_id = resp_signup_b.json()["id"]

        # Log in Alice
        resp_login_a = await http.post(
            "/auth/login",
            json={"email": email_a, "password": password},
        )
        assert resp_login_a.status_code == 200, resp_login_a.text
        token_a = resp_login_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Log in Bob
        resp_login_b = await http.post(
            "/auth/login",
            json={"email": email_b, "password": password},
        )
        assert resp_login_b.status_code == 200, resp_login_b.text
        token_b = resp_login_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # --- 2. Update Profiles ---
        resp_prof_a = await http.patch(
            "/auth/update_profile",
            json={"bio": "Alice bio", "age": 24, "gender": "female", "seeking": "male"},
            headers=headers_a,
        )
        assert resp_prof_a.status_code == 200, resp_prof_a.text

        resp_prof_b = await http.patch(
            "/auth/update_profile",
            json={"bio": "Bob bio", "age": 26, "gender": "male", "seeking": "female"},
            headers=headers_b,
        )
        assert resp_prof_b.status_code == 200, resp_prof_b.text

        # --- 3. Matching (Swipe & Mutual Match) ---
        # Alice likes Bob
        resp_swipe_a = await http.post(
            "/matching/swipe",
            json={"target_id": bob_id, "decision": "like"},
            headers=headers_a,
        )
        assert resp_swipe_a.status_code == 200, resp_swipe_a.text
        assert resp_swipe_a.json()["matched"] is False

        # Bob likes Alice -> triggers match
        resp_swipe_b = await http.post(
            "/matching/swipe",
            json={"target_id": alice_id, "decision": "like"},
            headers=headers_b,
        )
        assert resp_swipe_b.status_code == 200, resp_swipe_b.text
        swipe_data_b = resp_swipe_b.json()
        assert swipe_data_b["matched"] is True
        match_id = swipe_data_b["match_id"]
        assert match_id is not None

        # Verify match appears in Bob's matches list
        resp_matches = await http.get("/matching/matches", headers=headers_b)
        assert resp_matches.status_code == 200
        matches_items = resp_matches.json()["items"]
        assert any(m["match_id"] == match_id for m in matches_items)

        # --- 4. Chat + Real WebSocket Connection ---
        # Bob connects over a real TCP WebSocket connection (ADR-0018)
        async with websockets.connect(f"{WS_URL}?token={token_b}") as ws_bob:
            # 4a. Alice sends a message via HTTP REST
            client_msg_id = str(uuid.uuid4())
            resp_send = await http.post(
                f"/chat/{match_id}/messages",
                json={
                    "client_message_id": client_msg_id,
                    "content": "Hey Bob, nice to match!",
                },
                headers=headers_a,
            )
            assert resp_send.status_code == 201, resp_send.text
            msg_id = resp_send.json()["id"]

            # Bob receives real-time new_message frame over WebSocket
            raw_msg = await asyncio.wait_for(ws_bob.recv(), timeout=3.0)
            event_new = json.loads(raw_msg)
            assert event_new["event"] == "new_message"
            assert event_new["data"]["id"] == msg_id
            assert event_new["data"]["content"] == "Hey Bob, nice to match!"

            # 4b. Alice edits the message via HTTP REST
            resp_edit = await http.patch(
                f"/chat/messages/{msg_id}",
                json={"content": "Hey Bob, nice to match! (edited)"},
                headers=headers_a,
            )
            assert resp_edit.status_code == 200, resp_edit.text

            # Bob receives real-time message_edited frame
            raw_edit = await asyncio.wait_for(ws_bob.recv(), timeout=3.0)
            event_edit = json.loads(raw_edit)
            assert event_edit["event"] == "message_edited"
            assert event_edit["data"]["id"] == msg_id
            assert event_edit["data"]["content"] == "Hey Bob, nice to match! (edited)"

            # 4c. Alice deletes the message via HTTP REST
            resp_del = await http.delete(
                f"/chat/messages/{msg_id}",
                headers=headers_a,
            )
            assert resp_del.status_code == 204, resp_del.text

            # Bob receives real-time message_deleted frame
            raw_del = await asyncio.wait_for(ws_bob.recv(), timeout=3.0)
            event_del = json.loads(raw_del)
            assert event_del["event"] == "message_deleted"
            assert event_del["data"]["id"] == str(msg_id)

        # --- 5. Verify message is hard-deleted from chat history ---
        resp_list = await http.get(f"/chat/{match_id}/messages", headers=headers_b)
        assert resp_list.status_code == 200
        remaining_items = resp_list.json()["items"]
        assert all(m["id"] != msg_id for m in remaining_items)
