"""Weighted mixed-journey load test against a locally seeded DB.

Represents "typical service work" (spec.md §9): a user mostly browses the
feed and swipes, occasionally checks matches, and occasionally chats —
weighted so feed/swipe dominate, like real swiping behavior.

Requires the DB to already be seeded via scripts/seed_load_data.py (so
`load_user_<N>@loadtest.kpinderapp.com` / LoadTest123! accounts exist).
Run via `make load` (see Makefile) or directly:

    uv run locust -f loadtest/locustfile.py --host http://127.0.0.6:8000
"""

import itertools
import json
import os
import random
import threading

from locust import HttpUser, between, task

SEEDED_USERS = 50_000
PASSWORD = "LoadTest123!"

# Set by `make profile-isolated` / ad-hoc runs to isolate one slice's
# scalability from auth's login cost (see ai/audit/lab-5.md Part A) —
# tokens are pre-fetched once outside Locust, so on_start does no HTTP call.
_TOKENS_FILE = os.environ.get("KPINDER_PREFETCHED_TOKENS")
_tokens: list[str] = []
if _TOKENS_FILE:
    with open(_TOKENS_FILE) as f:
        _tokens = json.load(f)

_user_id_pool = itertools.cycle(range(SEEDED_USERS))
_token_pool = itertools.cycle(_tokens) if _tokens else None
_pool_lock = threading.Lock()


def _next_seeded_index() -> int:
    with _pool_lock:
        return next(_user_id_pool)


def _next_token() -> str:
    with _pool_lock:
        return next(_token_pool)


class KpinderUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        self.last_candidate_id: str | None = None
        self.last_match_id: str | None = None

        if _token_pool is not None:
            # Isolated mode: skip /auth/login entirely, reuse a pre-fetched token.
            self.client.headers.update({"Authorization": f"Bearer {_next_token()}"})
            return

        index = _next_seeded_index()
        email = f"load_user_{index}@loadtest.kpinderapp.com"
        resp = self.client.post(
            "/auth/login",
            json={"email": email, "password": PASSWORD},
            name="/auth/login",
        )
        if resp.status_code != 200:
            self.environment.runner.quit()
            raise RuntimeError(
                f"login failed for {email}: {resp.status_code} {resp.text}"
            )
        token = resp.json()["access_token"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})

    @task(10)
    def browse_feed(self) -> None:
        resp = self.client.get("/matching/feed", name="/matching/feed")
        if resp.status_code == 200:
            candidates = resp.json()
            if candidates:
                self.last_candidate_id = random.choice(candidates)["id"]

    @task(6)
    def swipe(self) -> None:
        if self.last_candidate_id is None:
            return
        decision = "like" if random.random() < 0.5 else "pass"
        self.client.post(
            "/matching/swipe",
            json={"target_id": self.last_candidate_id, "decision": decision},
            name="/matching/swipe",
        )
        self.last_candidate_id = None

    @task(3)
    def view_matches(self) -> None:
        resp = self.client.get("/matching/matches", name="/matching/matches")
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                self.last_match_id = random.choice(items)["match_id"]

    @task(2)
    def read_chat(self) -> None:
        if self.last_match_id is None:
            return
        self.client.get(
            f"/chat/{self.last_match_id}/messages", name="/chat/[match_id]/messages"
        )

    @task(1)
    def send_chat(self) -> None:
        if self.last_match_id is None:
            return
        import uuid

        self.client.post(
            f"/chat/{self.last_match_id}/messages",
            json={
                "content": "hey there — load test message",
                "client_message_id": str(uuid.uuid4()),
            },
            name="/chat/[match_id]/messages (send)",
        )
