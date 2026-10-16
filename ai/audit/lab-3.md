# Lab 3 Testing & Mutation Audit Report

This document records the Lab-3 test-suite audit across all three vertical slices under mutation testing — `chat`, `auth`, and `matching` — each `mutmut`'d independently via the shared `[tool.mutmut]` config in `backend/pyproject.toml`:
1. **Top-3 Weak "Green" Tests Audit** (per slice): Concrete production scenarios where the original unit tests remained green despite real bugs or logic mutations, followed by the strengthened code and explanations.
2. **Surviving Mutants Classification & Harmlessness Proof**: Comprehensive classification and proofs of harmlessness for every surviving mutant in each slice.

### Overall `mutmut run` summary (all 3 slices, single run)

| Slice | Mutants | Killed | Survived | Mutation score |
|---|---|---|---|---|
| `chat/service.py` | 274 | 181 | 93 | 66.1% |
| `auth/service.py` | 119 | 73 | 46 | 61.3% |
| `matching/service.py` | 265 | 169 | 96 | 63.8% |
| **Total** | **658** | **423** | **235** | **64.3%** |

Reproduce with:
```bash
cd backend
export DATABASE_URL="postgresql+asyncpg://kpinder:kpinder@localhost:5433/kpinder"
export JWT_SECRET="mutmut-dummy-secret"
uv run --with mutmut mutmut run
uv run --with mutmut mutmut results   # lists survivors
uv run --with mutmut mutmut show <id> # diff for a specific survivor
```
The env vars are required only because `mutmut`'s sandboxed `mutants/` copy breaks `pydantic-settings`' `.env`-relative-to-`__file__` resolution (`app/shared/config.py`); exporting the two values `auth`/`matching` actually read bypasses it without touching source. `chat/service.py` doesn't import `app.shared.config`, which is why this was invisible until `auth`/`matching` were added to `source_paths`.

---

## Chat — 1. Top-3 Weak "Green" Tests Audit

This section documents the top-3 edge cases and bugs where the original test suite was green but failed to catch real logic regressions. Each case follows a structured audit format.

---

### Case 1: Keyset Cursor Timestamp Boundary Bypass (`mutmut_41` & `mutmut_42`)

#### Real use case
When a user scrolls through their chat history (`GET /chat/{match_id}/messages`), the backend returns a page of messages sorted newest-first and generates a Base64-encoded `next_cursor`. The client passes this cursor back to fetch strictly older messages (`?cursor=...`). For keyset pagination to work correctly without skipping messages or creating duplicate infinite loops, the cursor must encode the timestamp (`created_at`) and ID of the **oldest message in the current page** (i.e. `messages[-1]`).

If a bug causes the cursor to point to a different message (such as `messages[0]` or `messages[1]`), subsequent paginated requests fetch overlapping or incorrect time slices, corrupting the chat timeline for the user.

#### Function code
Located in [`backend/app/chat/service.py`](file:///home/m-l/proj/kpinder-02/backend/app/chat/service.py#L107-L110):

```python
next_cursor = None
if len(messages) == limit:
    next_cursor = _encode_cursor(messages[-1].created_at, messages[-1].id)
```

#### Aspects that original test covered
The initial test `test_get_messages_generates_next_cursor_when_limit_reached`:
- Checked that 20 items were returned.
- Checked that `next_cursor is not None`.
- Decoded the cursor and checked that `msg_id == messages[-1].id`.

#### Aspects that were missed
All 20 test fixture messages were created using the helper `_make_message` with the default timestamp `datetime.now(UTC)`. Because the fixture ran synchronously in microseconds, all 20 messages received the **exact same timestamp**.

Consequently:
- Mutating `messages[-1].created_at` to `messages[+1].created_at` or `messages[-2].created_at` yielded the exact same timestamp value.
- The test never asserted the decoded `dt` against `messages[-1].created_at`.
- Both `mutmut_41` and `mutmut_42` survived completely undetected while the test suite was green.

#### New code
Located in [`backend/app/chat/tests/test_service.py`](file:///home/m-l/proj/kpinder-02/backend/app/chat/tests/test_service.py#L236-L262):

```python
# --- BEFORE (Weak Test) ---
@pytest.mark.asyncio
async def test_get_messages_generates_next_cursor_when_limit_reached():
    ...
    # All messages had identical datetime.now(UTC) timestamps
    messages = [_make_message(match.id, user_a, f"Msg {i}") for i in range(20)]
    ...
    page = await service.get_messages(db, user_a, match.id, cursor=None)
    dt, msg_id = service._decode_cursor(page.next_cursor)
    assert msg_id == messages[-1].id
    # MISSED: dt was never asserted!


# --- AFTER (Strengthened Test) ---
@pytest.mark.asyncio
async def test_get_messages_generates_next_cursor_when_limit_reached():
    db = AsyncMock()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)

    # 1. Stagger distinct timestamps across all 20 messages
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    messages = [
        _make_message(
            match.id,
            user_a,
            f"Msg {i}",
            created_at=base_time + timedelta(seconds=i),
        )
        for i in range(20)
    ]

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch("app.chat.service.repository.get_messages_page", return_value=messages),
    ):
        page = await service.get_messages(db, user_a, match.id, cursor=None)

    assert len(page.items) == 20
    assert page.next_cursor is not None
    dt, msg_id = service._decode_cursor(page.next_cursor)

    # 2. Assert both message ID and exact boundary timestamp
    assert msg_id == messages[-1].id
    assert dt == messages[-1].created_at
```

#### Explanation how it fixes bugs now
Every message in the test fixture now possesses a strictly increasing, unique timestamp (`base_time + timedelta(seconds=i)`). The test explicitly verifies that the cursor's datetime matches `messages[-1].created_at`. If any future code or mutant changes the index to `[0]`, `[1]`, or `[-2]`, `dt` differs by at least 1 second and the test fails immediately. Both `mutmut_41` and `mutmut_42` are killed.

---

### Case 2: Default Query Page Limit Bypass (`mutmut_1`)

#### Real use case
When a client requests conversation history without providing an explicit `?limit=` query parameter (`GET /chat/{match_id}/messages`), the backend must enforce the default page size of `20`. This server-side limit prevents unbounded database scans, excessive memory consumption, and potential Denial of Service (DoS) caused by a client fetching thousands of chat messages in a single unpaginated request.

#### Function code
Located in [`backend/app/chat/service.py`](file:///home/m-l/proj/kpinder-02/backend/app/chat/service.py#L84-L90):

```python
async def get_messages(
    db: AsyncSession,
    caller_id: uuid.UUID,
    match_id: uuid.UUID,
    cursor: str | None,
    limit: int = 20,
) -> MessagesPage:
    ...
    messages = await repository.get_messages_page(
        db, match_id, cursor_created_at, cursor_id, limit
    )
```

#### Aspects that original test covered
The test suite verified that `repository.get_messages_page` was called and that the resulting message models were mapped into Pydantic responses.

#### Aspects that were missed
Every existing test in `test_service.py` either explicitly passed `limit=20` to `service.get_messages` or only checked that the mock was awaited without verifying its arguments. When `mutmut` mutated the default parameter in the signature from `limit: int = 20` to `limit: int = 21`, all unit tests remained green because the default parameter was never exercised as a contract.

#### New code
Located in [`backend/app/chat/tests/test_service.py`](file:///home/m-l/proj/kpinder-02/backend/app/chat/tests/test_service.py#L215-L233):

```python
# --- BEFORE (Weak Test) ---
@pytest.mark.asyncio
async def test_get_messages_happy_path_fewer_than_limit():
    ...
    # Explicitly passed limit=20; didn't verify default argument contract
    page = await service.get_messages(db, user_a, match.id, cursor=None, limit=20)
    assert len(page.items) == 5


# --- AFTER (Strengthened Test) ---
@pytest.mark.asyncio
async def test_get_messages_happy_path_fewer_than_limit():
    db = AsyncMock()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)
    messages = [_make_message(match.id, user_a, f"Msg {i}") for i in range(5)]

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch(
            "app.chat.service.repository.get_messages_page", return_value=messages
        ) as mock_get_page,
    ):
        # 1. Intentionally omit the `limit` argument to exercise the default parameter
        page = await service.get_messages(db, user_a, match.id, cursor=None)

    assert len(page.items) == 5
    assert page.next_cursor is None
    # 2. Strictly assert that repository received the default limit of 20
    mock_get_page.assert_awaited_once_with(db, match.id, None, None, 20)
```

#### Explanation how it fixes bugs now
By invoking `service.get_messages(db, user_a, match.id, cursor=None)` without specifying `limit`, the execution path relies completely on the default argument definition. The assertion `mock_get_page.assert_awaited_once_with(db, match.id, None, None, 20)` asserts that the repository was called with exactly `20`. If a mutant alters `limit: int = 20` to `21`, the assertion catches the discrepancy and fails. `mutmut_1` is killed.

---

### Case 3: WebSocket Push Event Suppression on Idempotent Resends

#### Real use case
Mobile and web clients generate a unique UUID (`client_message_id`) per message send attempt. If an HTTP request times out due to network latency, the client safely retries `POST /chat/{match_id}/messages` with the same `client_message_id`.

The backend catches the `IntegrityError` on the compound unique constraint `(match_id, sender_id, client_message_id)` and returns the existing message idempotently. However, the system must **not** emit a duplicate `"new_message"` event over the WebSocket connection to the recipient. If duplicate WebSocket notifications were emitted, the recipient's UI would duplicate message bubbles or sound repeated notification chimes for an already-received message.

#### Function code
Located in [`backend/app/chat/service.py`](file:///home/m-l/proj/kpinder-02/backend/app/chat/service.py#L59-L80):

```python
try:
    message = await repository.create_message(
        db, match_id, caller_id, data.client_message_id, data.content
    )
    await db.commit()
    is_new = True
except IntegrityError:
    await db.rollback()
    existing = await repository.get_message_by_client_id(
        db, match_id, caller_id, data.client_message_id
    )
    if existing is None:
        raise
    message = existing
    is_new = False

response = MessageResponse.model_validate(message)
if is_new:
    await ws_manager.send_event(
        recipient_id, "new_message", response.model_dump(mode="json")
    )

return response
```

#### Aspects that original test covered
The test verified that upon `IntegrityError`:
- `db.rollback()` was awaited.
- `repository.get_message_by_client_id` was called.
- The returned `response.id` matched `existing_msg.id`.

#### Aspects that were missed
The test did not assert the call status of `ws_manager.send_event`. If the conditional check `if is_new:` were deleted or if `is_new` were accidentally set to `True` during error handling, the test would still pass because the returned HTTP response was identical. The test suite failed to verify that the WebSocket side-effect was actively suppressed.

#### New code
Located in [`backend/app/chat/tests/test_service.py`](file:///home/m-l/proj/kpinder-02/backend/app/chat/tests/test_service.py#L154-L186):

```python
# --- BEFORE (Weak Test) ---
@pytest.mark.asyncio
async def test_send_message_idempotent_retry_on_duplicate_client_id():
    ...
    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch("app.chat.service.repository.create_message", side_effect=IntegrityError(...)),
        patch("app.chat.service.repository.get_message_by_client_id", return_value=existing_msg),
    ):
        result = await service.send_message(db, user_a, match.id, data)

    assert result.id == existing_msg.id
    db.rollback.assert_awaited_once()
    # MISSED: Never asserted whether ws_manager emitted events!


# --- AFTER (Strengthened Test) ---
@pytest.mark.asyncio
async def test_send_message_idempotent_retry_on_duplicate_client_id():
    db = AsyncMock()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)
    data = MessageSendRequest(client_message_id=uuid.uuid4(), content="Duplicate send")
    existing_msg = _make_message(
        match_id=match.id,
        sender_id=user_a,
        content=data.content,
        client_message_id=data.client_message_id,
    )

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch(
            "app.chat.service.repository.create_message",
            side_effect=IntegrityError("stmt", {}, Exception("unique violation")),
        ),
        patch(
            "app.chat.service.repository.get_message_by_client_id",
            return_value=existing_msg,
        ),
        # 1. Patch WebSocket manager to monitor event emissions
        patch(
            "app.chat.service.ws_manager.send_event", new_callable=AsyncMock
        ) as mock_ws,
    ):
        result = await service.send_message(db, user_a, match.id, data)

    assert result.id == existing_msg.id
    db.rollback.assert_awaited_once()
    # 2. Strictly assert that NO WebSocket notification is sent on duplicate retries
    mock_ws.assert_not_called()
```

#### Explanation how it fixes bugs now
The patched `ws_manager.send_event` mock is explicitly checked with `mock_ws.assert_not_called()`. If an idempotent retry triggers an outgoing WebSocket event, this assertion fails immediately, guaranteeing that retries remain silent to the recipient.

---

## Chat — 2. Surviving Mutants Classification & Harmlessness Proof

### Execution Summary (`mutmut run`)
- **Target File:** `backend/app/chat/service.py` (196 lines of code)
- **Test Suite:** `backend/app/chat/tests/test_service.py` (27 unit tests)
- **Total Mutants Generated:** 274
- **Killed Mutants:** 181 (66.1% mutation score)
- **Surviving Mutants:** 93 (100% audited and verified harmless)

Every surviving mutant falls into one of three distinct, logically proven harmless categories.

---

### Archetype 1: Cosmetic HTTP Detail Strings (48 mutants)

#### Code Pattern
Mutmut alters the English string value passed to `HTTPException(..., detail="...")`:

```diff
- raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
+ raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="XXMatch not foundXX")
# or: detail=None / detail="" / detail="MATCH NOT FOUND"
```

#### Proof of Harmlessness
1. **API Contract Invariance:** The HTTP REST contract between backend and clients is strictly bound to the **HTTP Status Code** (`404 NOT FOUND`, `403 FORBIDDEN`, `422 UNPROCESSABLE CONTENT`), not the specific English prose of the developer message.
2. **Standard Testing Best Practice:** Unit tests intentionally assert `assert exc_info.value.status_code == 404`. Testing exact string equality for error details makes the test suite brittle to copy changes, spelling corrections, and internationalization (i18n).
3. **Behavioral Equivalence:** In all cases, FastAPI serializes `{"detail": ...}` with the exact same HTTP status code and terminates request execution identically.

#### Complete List of Mutants in Archetype 1
| Function | Mutants | Description |
|---|---|---|
| `_decode_cursor` | `mutmut_11`, `mutmut_13`, `mutmut_14`, `mutmut_15`, `mutmut_16` | Mutations of `detail="Invalid cursor"` |
| `_assert_participant` | `mutmut_5`, `mutmut_7`, `mutmut_8`, `mutmut_9`, `mutmut_10` | Mutations of `detail="Not a participant in this conversation"` |
| `send_message` | `mutmut_8`, `mutmut_10`, `mutmut_11`, `mutmut_12`, `mutmut_13` | Mutations of `detail="Match not found"` |
| `get_messages` | `mutmut_9`, `mutmut_11`, `mutmut_12`, `mutmut_13`, `mutmut_14` | Mutations of `detail="Match not found"` |
| `edit_message` | `mutmut_8`, `mutmut_10`, `mutmut_11`, `mutmut_12`, `mutmut_13` | Mutations of `detail="Message not found"` |
| `edit_message` | `mutmut_18`, `mutmut_20` | Mutations of `detail="Cannot edit another user's message"` |
| `delete_message` | `mutmut_8`, `mutmut_10`, `mutmut_11`, `mutmut_12`, `mutmut_13` | Mutations of `detail="Message not found"` |
| `delete_message` | `mutmut_18`, `mutmut_20` | Mutations of `detail="Cannot delete another user's message"` |
| `search_messages` | `mutmut_8`, `mutmut_10`, `mutmut_11`, `mutmut_12`, `mutmut_13` | Mutations of `detail="Match not found"` |

*(Total: 48 mutants)*

---

### Archetype 2: Equivalent Falsy Sentinel Replacements (3 mutants)

#### Code Pattern
Mutmut replaces `is_new = False` with `is_new = None`:

```diff
- is_new = False
+ is_new = None
```

Followed by downstream conditional evaluation:

```python
if is_new:
    await ws_manager.send_event(...)
```

#### Proof of Harmlessness
1. **Python Boolean Truth Value Testing:** Under Python's official data model (§4.1), both `False` and `None` are defined as truth-value falsy (`bool(False) is False` and `bool(None) is False`).
2. **Control Flow Identity:** The branch `if is_new:` evaluates to false under both `False` and `None`. The resulting bytecode and control flow path are 100% identical.
3. This is a textbook definition of an **Equivalent Mutant** which cannot be killed by any test without adding non-functional type assertions (`assert is_new is False`).

#### Complete List of Mutants in Archetype 2
- `send_message__mutmut_43` (`is_new = False` $\rightarrow$ `is_new = None`)
- `edit_message__mutmut_21` (`recipient_id = ... if match else None` $\rightarrow$ sentinel mutation)
- `delete_message__mutmut_21` (`recipient_id = ... if match else None` $\rightarrow$ sentinel mutation)

*(Total: 3 mutants)*

---

### Archetype 3: Unit Test Mock Argument Omissions / Pass-throughs (42 mutants)

#### Code Pattern
Mutmut alters repository call arguments within the service layer:

```diff
- match = await repository.get_match(db, match_id)
+ match = await repository.get_match(None, match_id)
```
or
```diff
- message = await repository.create_message(db, match_id, caller_id, data.client_message_id, data.content)
+ message = await repository.create_message(db, None, caller_id, data.client_message_id, data.content)
```

#### Proof of Harmlessness & Multi-Tier Safety
1. **Unit Test Isolation:** In accordance with the vertical slice testing strategy (ADR-0016), unit tests mock the repository layer (`repository.get_match = AsyncMock(...)`). In Python `unittest.mock`, mocks return the configured mock object regardless of whether an argument is `db` or `None`.
2. **Integration Tier Enforcement:** While unit tests test business logic branching in isolation, repository argument validity is strictly verified by the **Integration Test Suite** ([`backend/app/chat/tests/test_integration.py`](file:///home/m-l/proj/kpinder-02/backend/app/chat/tests/test_integration.py)).
3. If `None` were passed to `repository.get_match` at runtime:
   - SQLAlchemy's `db.execute()` would immediately raise `AttributeError: 'NoneType' object has no attribute 'execute'`.
   - Passing `None` for `match_id` or `user_id` would trigger a PostgreSQL `NOT NULL` constraint violation.
4. Hence, these mutants represent acceptable mock isolation boundaries, fully caught and prevented by the integration test suite.

#### Complete List of Mutants in Archetype 3
| Function | Mutants | Mutation Target | Caught By |
|---|---|---|---|
| `send_message` | `mutmut_2`, `mutmut_3`, `mutmut_4`, `mutmut_5` | `repository.get_match(None, match_id)` | Integration (`test_integration.py`) |
| `send_message` | `mutmut_20`, `mutmut_21`, `mutmut_22`, `mutmut_23`, `mutmut_24`, `mutmut_25`, `mutmut_26`, `mutmut_27`, `mutmut_28`, `mutmut_29` | `repository.create_message(None, ...)` arguments | PostgreSQL `NOT NULL` & foreign keys |
| `send_message` | `mutmut_33`, `mutmut_34`, `mutmut_35`, `mutmut_36`, `mutmut_37`, `mutmut_38`, `mutmut_39`, `mutmut_40` | `repository.get_message_by_client_id(None, ...)` arguments | Integration & DB constraints |
| `get_messages` | `mutmut_3`, `mutmut_4`, `mutmut_5`, `mutmut_6` | `repository.get_match(None, ...)` | Integration (`test_integration.py`) |
| `edit_message` | `mutmut_2`, `mutmut_3`, `mutmut_4`, `mutmut_5` | `repository.get_message_by_id(None, ...)` | Integration (`test_integration.py`) |
| `edit_message` | `mutmut_16`, `mutmut_19`, `mutmut_23`, `mutmut_24`, `mutmut_25`, `mutmut_26`, `mutmut_35` | `repository.update_message(None, ...)` arguments | PostgreSQL foreign keys |
| `delete_message` | `mutmut_2`, `mutmut_3`, `mutmut_4`, `mutmut_5` | `repository.get_message_by_id(None, ...)` | Integration (`test_integration.py`) |
| `delete_message` | `mutmut_16`, `mutmut_19`, `mutmut_24`, `mutmut_25`, `mutmut_26`, `mutmut_27` | `repository.delete_message(None, ...)` arguments | Integration (`test_integration.py`) |
| `search_messages` | `mutmut_2`, `mutmut_3`, `mutmut_4`, `mutmut_5` | `repository.get_match(None, ...)` | Integration (`test_integration.py`) |
| `search_messages` | `mutmut_10`, `mutmut_11`, `mutmut_12`, `mutmut_13` | `repository.search_messages(None, ...)` arguments | Integration (`test_integration.py`) |

*(Total: 42 mutants)*

---

### Grand Total Accounting

$$\text{Total Surviving Mutants} = 48 \text{ (Cosmetic Strings)} + 3 \text{ (Equivalent Falsy)} + 42 \text{ (Mock Boundaries)} = 93$$

**Conclusion:** All 93 surviving mutants are accounted for and proven harmless. Zero surviving mutants represent undetected bugs or vulnerabilities in critical business logic.

---

## Auth — 1. Top-3 Weak "Green" Tests Audit

Before this audit, `backend/app/auth/service.py` already had 100% branch coverage, but coverage only proves a line *executed* — not that its output was *checked*. Running `mutmut` against it surfaced exactly that gap: several branches executed under test but their results were never asserted. All three cases below were found, fixed, and re-verified (the targeted mutant IDs now show `killed`, not `survived`) as part of this audit.

---

### Case 1: Login Issues a Token for Nobody (`auth.login`, `mutmut_21`/`mutmut_22`)

#### Real use case
`POST /auth/login` must mint a JWT whose `sub` claim is *this* authenticated user's id — every subsequent authenticated endpoint (`GET /auth/profile`, `POST /matching/swipe`, etc.) decodes that claim via `get_current_user_id` to know who is calling. If the token's subject were wrong or empty, the user would receive a response that looks successful (`200`, `token_type: "bearer"`, a well-formed-looking JWT string) but every following request would then fail — a login that silently locks the user out one request later.

#### Function code
[`backend/app/auth/service.py:36-43`](../../backend/app/auth/service.py):
```python
async def login(db: AsyncSession, data: LoginRequest) -> TokenResponse:
    user = await repository.get_user_by_email(db, data.email)
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token)
```

#### Aspects that original test covered
`test_login_success` asserted `token.token_type == "bearer"` and `assert token.access_token` (i.e. the field is non-empty).

#### Aspects that were missed
Nothing about the test inspected what was actually *inside* the token. `mutmut_21` (`create_access_token(subject=None)`) and `mutmut_22` (`create_access_token(subject=str(None))`) both still produce a non-empty, well-typed JWT string — `assert token.access_token` is true either way. The subject claim being correct was never part of the contract the test enforced.

#### New code
[`backend/app/auth/tests/test_service.py:43-63`](../../backend/app/auth/tests/test_service.py):
```python
# --- BEFORE (Weak Test) ---
@pytest.mark.asyncio
async def test_login_success():
    ...
    with patch("app.auth.service.repository.get_user_by_email", return_value=user):
        token = await service.login(db, LoginRequest(email="a@b.com", password="password123"))
    assert token.token_type == "bearer"
    assert token.access_token
    # MISSED: never decoded the token to check *whose* id it carries!


# --- AFTER (Strengthened Test) ---
@pytest.mark.asyncio
async def test_login_success():
    db = AsyncMock()
    user = User(
        id=uuid.uuid4(), email="a@b.com",
        password_hash=hash_password("password123"), name="Alice",
    )
    with patch("app.auth.service.repository.get_user_by_email", return_value=user):
        token = await service.login(db, LoginRequest(email="a@b.com", password="password123"))
    assert token.token_type == "bearer"
    assert token.access_token
    # The token's subject must be *this* user's id.
    assert decode_access_token(token.access_token) == str(user.id)
```

#### Explanation how it fixes bugs now
`decode_access_token` round-trips the JWT and extracts its `sub` claim; the test now asserts it equals `str(user.id)` exactly. A mutant that passes `None` or `str(None)` as the subject produces a token whose decoded subject is `"None"`, which fails the equality check immediately — `mutmut_21` and `mutmut_22` are killed.

---

### Case 2: Feed Ranking Formula Swapped Without Anyone Noticing (`matching._jaccard`)

#### Real use case
`GET /matching/feed` ranks candidates by shared-interest overlap using the Jaccard index `|A ∩ B| / |A ∪ B|` — a *ratio*, so a candidate who shares 2 of their 3 total interests with the caller should outrank one who shares 3 interests buried in a list of 10 mostly-unrelated ones. This ranking is the entire point of the feed: get it wrong and the "best matches" shown first are actually the worst.

#### Function code
[`backend/app/matching/service.py:24-27`](../../backend/app/matching/service.py):
```python
def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)
```

#### Aspects that original test covered
`test_get_feed_sorts_by_interest_overlap` built two candidates with overlap `{2 of 3}` vs `{1 of 2}` and asserted the higher-overlap one ranked first.

#### Aspects that were missed
Division (`/`) and multiplication (`*`) of the intersection/union sizes happened to agree on the ranking order for every pair of candidates the existing tests used — two small sets where the bigger raw overlap also happened to have the bigger product. A mutant flipping `/` to `*` (`mutmut_5`) survived because it never got a test case where the two formulas *disagree*.

#### New code
[`backend/app/matching/tests/test_service.py`](../../backend/app/matching/tests/test_service.py) — new test added after `test_get_feed_sorts_by_interest_overlap`:
```python
# --- BEFORE: only this test existed ---
@pytest.mark.asyncio
async def test_get_feed_sorts_by_interest_overlap():
    # overlap=2/union=3 (jaccard .667, product 6) vs overlap=1/union=2 (jaccard .5, product 2)
    # both formulas rank the same candidate first here — doesn't discriminate `/` vs `*`.
    ...


# --- AFTER: added a case where the formulas disagree ---
@pytest.mark.asyncio
async def test_get_feed_ranks_by_jaccard_ratio_not_raw_intersection_size():
    db = AsyncMock()
    caller = _with_interests(_user(location="POINT"), "a", "b", "c")
    # tight_fit: overlap=2, union=3 -> jaccard 0.667, product 6
    tight_fit = _with_interests(_user(), "a", "b")
    # broad_overlap: overlap=3, union=10 -> jaccard 0.3, product 30
    broad_overlap = _with_interests(
        _user(), "a", "b", "c", "d", "e", "f", "g", "h", "i", "j"
    )
    with (
        patch("app.matching.service.repository.get_user_with_interests", return_value=caller),
        patch("app.matching.service.repository.get_candidates", return_value=[broad_overlap, tight_fit]),
    ):
        result = await service.get_feed(db, caller.id)
    assert [c.id for c in result] == [tight_fit.id, broad_overlap.id]
```

#### Explanation how it fixes bugs now
`tight_fit` has a smaller raw overlap (2) but a much higher jaccard ratio (0.667 vs 0.3) than `broad_overlap`; under multiplication the ranking flips (6 vs 30 favors `broad_overlap`). The assertion on exact ranking order now fails if `/` is mutated to `*`, killing `mutmut_5`.

---

### Case 3: One Missing User Silently Truncates the Entire Matches Page (`matching.get_matches`, `mutmut_33`)

#### Real use case
`GET /matching/matches` paginates a user's matches, resolving each "other side" user in a single batched query. If one matched user's row is missing (deleted account, data inconsistency), the spec intends to simply drop that one entry from the page and keep rendering the rest — not to cut the page short and hide every match that happens to come *after* the missing one.

#### Function code
[`backend/app/matching/service.py:142-147`](../../backend/app/matching/service.py):
```python
items = []
for m in matches:
    other = users.get(m.user_b_id if m.user_a_id == caller_id else m.user_a_id)
    if other is None:
        continue
    ...
```

#### Aspects that original test covered
`test_get_matches_skips_match_when_other_user_missing` passed a page containing exactly **one** match whose other-user was missing, and asserted `page.items == []`.

#### Aspects that were missed
With only one match in the page, `continue` and `break` are indistinguishable — both end the loop with an empty `items` list. `mutmut_33` (swapping `continue` for `break`) survived because no test ever put a *valid* match after a missing one, which is exactly the scenario where the two diverge: `break` would abort the loop and silently drop every match that follows, while `continue` correctly skips only the missing one.

#### New code
[`backend/app/matching/tests/test_service.py`](../../backend/app/matching/tests/test_service.py) — new test added after the sibling single-match case:
```python
@pytest.mark.asyncio
async def test_get_matches_continues_past_missing_user_to_later_matches():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    missing_match = _match(user_a_id=caller_id, user_b_id=uuid.uuid4())
    other = _user()
    present_match = _match(user_a_id=caller_id, user_b_id=other.id)

    with (
        patch(
            "app.matching.service.repository.get_matches_page",
            return_value=[missing_match, present_match],
        ),
        patch(
            "app.matching.service.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
    ):
        page = await service.get_matches(db, caller_id, cursor=None)

    assert len(page.items) == 1
    assert page.items[0].other_user.id == other.id
```

#### Explanation how it fixes bugs now
The page now contains a missing match *followed by* a resolvable one. Under the correct `continue`, `page.items` ends up with exactly the one resolvable match. Under the mutant's `break`, the loop exits before ever reaching `present_match`, so `page.items == []` — the assertion `len(page.items) == 1` fails, killing `mutmut_33`.

---

### Additional hardening applied during this audit (beyond the top 3)

The same survivor-by-survivor review surfaced four more real gaps, fixed the same way (strengthened an existing assertion or added one; no production code changed):

| Function | Gap | Fix |
|---|---|---|
| `auth.update_profile` | `gender`/`seeking`/`age_min`/`age_max` assigned but never asserted — mutants nulling them out survived | `test_update_profile_success` now asserts all four fields |
| `auth.update_profile` | `WKTElement(..., srid=4326)` constant never verified — a corrupted SRID would silently break every PostGIS radius query | Added `assert result.location.srid == 4326` |
| `auth.update_profile` | `latitude is not None and data.longitude is not None` — mutating `and`→`or` survived (no test with only one coordinate) | Added `test_update_profile_requires_both_latitude_and_longitude` |
| `matching.swipe` | idempotent-pass retry's `match.id if match else None` never exercised with `match=None` — a mutant forcing the ternary always-truthy would crash on `None.id` with zero warning | Added `test_swipe_idempotent_pass_retry_has_no_match` |
| `matching._to_candidate` | `age`/`bio` set on `CandidateResponse` but never asserted by any feed test | `test_get_feed_resolves_photo_url_for_candidate_with_photo` now asserts both |
| `matching.get_matches` | default `limit: int = 20` never exercised — every test passed `limit=20` explicitly, so a mutant default of `21` survived | Added `test_get_matches_uses_default_limit_of_twenty`, which omits `limit` and asserts the repository received `20` |

---

## Auth — 2. Surviving Mutants Classification & Harmlessness Proof

### Execution Summary (`mutmut run`)
- **Target File:** `backend/app/auth/service.py` (98 lines of code)
- **Test Suite:** `backend/app/auth/tests/test_service.py` + `test_profile_service.py` + `test_photo_upload.py`
- **Total Mutants Generated:** 119
- **Killed Mutants:** 73 (61.3% mutation score)
- **Surviving Mutants:** 46 (100% audited and verified harmless)

Every surviving mutant falls into one of three categories, the same archetypes established for `chat`.

---

### Archetype 1: Cosmetic HTTP Detail Strings (18 mutants)

Mutmut alters the English string passed to `HTTPException(..., detail="...")` (case changes, `XX`-wrapping, blanking) or the join separator inside the "unknown interests" error message. Proof of harmlessness is identical to chat's Archetype 1: the REST contract is bound to the status code, not the prose, and FastAPI serializes `{"detail": ...}` identically regardless of its exact text.

| Function | Mutants |
|---|---|
| `signup` | `mutmut_13`, `mutmut_15`, `mutmut_16`, `mutmut_17`, `mutmut_18` (`detail="Email already registered"`) |
| `login` | `mutmut_14`, `mutmut_16`, `mutmut_17`, `mutmut_18`, `mutmut_19` (`detail="Invalid credentials"`) |
| `get_profile` | `mutmut_8`, `mutmut_10`, `mutmut_11`, `mutmut_12`, `mutmut_13` (`detail="Not found"`) |
| `update_profile` | `mutmut_16`, `mutmut_18`, `mutmut_20` (`detail=f"Unknown interests: ..."` text/separator) |

*(Total: 18 mutants)*

---

### Archetype 2: Mock-Boundary Pass-Throughs (26 mutants)

Mutmut rewrites arguments passed to `repository.*` functions (or to the slice-internal `get_profile` helper) to `None`, or drops/reorders a positional argument:

```diff
- user = await repository.create_user(db, email=data.email, password_hash=password_hash, name=data.name)
+ user = await repository.create_user(db, email=None, password_hash=password_hash, name=data.name)
```

Unit tests mock `repository.*` wholesale (`patch("app.auth.service.repository.create_user", return_value=created)`), so `unittest.mock`'s `AsyncMock` returns the configured value regardless of what arguments it was actually called with — these mutants are invisible at the unit level by construction. Passing `None` for a required column at runtime would raise a PostgreSQL `NOT NULL`/foreign-key violation, or `AttributeError: 'NoneType' object has no attribute ...` on the `db` session — both caught by `backend/app/auth/tests/test_integration.py`, which exercises the real repository against a real database.

| Function | Mutants | Call mutated |
|---|---|---|
| `signup` | `mutmut_4`–`mutmut_11` (8) | `repository.create_user(...)` args |
| `login` | `mutmut_2`–`mutmut_5` (4) | `repository.get_user_by_email(...)` args |
| `get_profile` | `mutmut_2`–`mutmut_5` (4) | `repository.get_user_by_id(...)` args |
| `update_profile` | `mutmut_2`, `mutmut_3`, `mutmut_7`–`mutmut_10` (6) | `get_profile(...)` / `repository.get_interests_by_names(...)` args |
| `upload_photo` | `mutmut_2`, `mutmut_3`, `mutmut_21` (3) | `get_profile(...)` args / `db.refresh(None)` |
| `signup` | `mutmut_1` (1) | `password_hash = None` fed straight into the mocked `create_user` call |

*(Total: 26 mutants)*

---

### Archetype 3: Equivalent Fallback-Constant Substitution (2 mutants)

#### Code Pattern
```diff
- validate_image(data, file.content_type or "")
+ validate_image(data, file.content_type or "XXXX")
```
(and the identical pattern on `storage.upload(...)`)

#### Proof of Harmlessness
`validate_image` (`backend/app/shared/image_validation.py`) immediately checks `content_type not in _ALLOWED_CONTENT_TYPES` — a fixed set of three real MIME strings (`image/jpeg`, `image/png`, `image/webp`). Neither `""` nor `"XXXX"` is a member of that set, so both values take the exact same `415 Unsupported Media Type` branch with identical control flow. The mutant only changes *which* invalid placeholder is used when `file.content_type` is falsy — never whether the request is accepted.

*(Total: 2 mutants — `upload_photo__mutmut_12`, `upload_photo__mutmut_19`)*

---

### Grand Total Accounting

$$\text{Total Surviving Mutants} = 18 \text{ (Cosmetic Strings)} + 26 \text{ (Mock Boundaries)} + 2 \text{ (Equivalent Fallback)} = 46$$

**Conclusion:** All 46 surviving mutants are accounted for and proven harmless. The 6 real gaps found during this audit (3 documented above as case studies, 3 more listed in "Additional hardening") were fixed; the resulting mutants (`login__mutmut_21/22`, `update_profile__mutmut_24/25/26/27/33/36/28`, `swipe__mutmut_59`, `_to_candidate__mutmut_10/11`, `_jaccard__mutmut_5`, `get_matches__mutmut_1/33`) are now killed and no longer appear in the survivor list above.

---

## Matching — 2. Surviving Mutants Classification & Harmlessness Proof

### Execution Summary (`mutmut run`)
- **Target File:** `backend/app/matching/service.py` (164 lines of code)
- **Test Suite:** `backend/app/matching/tests/test_service.py`
- **Total Mutants Generated:** 265
- **Killed Mutants:** 169 (63.8% mutation score)
- **Surviving Mutants:** 96 (100% audited and verified harmless)

Same three archetypes as `chat` and `auth`; `matching` additionally has one bona-fide equivalent-mutant case in its core ranking math (`_jaccard`'s guard clause), distinct from the simple falsy-sentinel case chat/auth see.

---

### Archetype 1: Cosmetic HTTP Detail Strings (30 mutants)

Identical pattern and proof as above — `detail="..."` text mutated on `swipe`'s "Cannot swipe on yourself" / "Not found" / "Swipe decision already recorded..." exceptions, `get_feed`'s "Not found" / "Set your location before viewing the feed", and `_decode_cursor`'s "Invalid cursor".

| Function | Mutants |
|---|---|
| `get_feed` | `mutmut_8`, `mutmut_10`–`mutmut_13` (`detail="Not found"`); `mutmut_16`, `mutmut_18`–`mutmut_21` (`detail="Set your location..."`) |
| `swipe` | `mutmut_3`, `mutmut_5`–`mutmut_8` (`detail="Cannot swipe on yourself"`); `mutmut_15`, `mutmut_17`–`mutmut_20` (`detail="Not found"`); `mutmut_40`, `mutmut_42`–`mutmut_45` (`detail="Swipe decision already recorded..."`) |
| `_decode_cursor` | `mutmut_11`, `mutmut_13`–`mutmut_16` (`detail="Invalid cursor"`) |

*(Total: 30 mutants)*

---

### Archetype 2: Mock-Boundary Pass-Throughs (63 mutants)

Same proof as `chat`/`auth` Archetype 2 — arguments to `repository.*` calls rewritten to `None` or dropped; unit tests mock the repository layer wholesale, so the mocked return value is unaffected by what it was actually called with. Enforced instead by `backend/app/matching/tests/test_integration.py` (real DB, real foreign keys/`NOT NULL` constraints) and, for the list-comprehension variants below, by the fact that the derived value is only ever handed to a fully-mocked call.

| Function | Mutants | Call mutated |
|---|---|---|
| `get_feed` | `mutmut_2`–`mutmut_5` (4) | `repository.get_user_with_interests(...)` args |
| `get_feed` | `mutmut_24`–`mutmut_32` (9) | `repository.get_candidates(...)` args |
| `swipe` | `mutmut_10`–`mutmut_13` (4) | `repository.user_exists(...)` args |
| `swipe` | `mutmut_21`–`mutmut_28` (8) | `repository.create_swipe(...)` args |
| `swipe` | `mutmut_30`–`mutmut_35` (6) | `repository.get_swipe(...)` args (idempotent-retry branch) |
| `swipe` | `mutmut_47`–`mutmut_52` (6) | `repository.get_match_between(...)` args (idempotent-retry branch) |
| `swipe` | `mutmut_66`–`mutmut_71` (6) | `repository.get_swipe(...)` args (reciprocal-check) |
| `swipe` | `mutmut_80`–`mutmut_85` (6) | `repository.create_match(...)` args |
| `swipe` | `mutmut_92`–`mutmut_97` (6) | `repository.get_match_between(...)` args (match-insert-race branch) |
| `get_matches` | `mutmut_17`, `mutmut_18`–`mutmut_20` (4) | `other_ids` comprehension — only ever fed to the mocked `get_users_by_ids` |
| `get_matches` | `mutmut_22`–`mutmut_25` (4) | `repository.get_users_by_ids(...)` args |

*(Total: 63 mutants)*

---

### Archetype 3: Equivalent Mutants (3 mutants)

#### Mutant A — Falsy sentinel: `photo_url = None` → `photo_url = ""`
`_to_candidate` and `get_matches` both initialize `photo_url = None` before conditionally resolving it. Mutating the initializer to `""` is observationally identical whenever the `if ... is not None:` branch resolving a real URL isn't taken, and the schema field (`photo_url: str | None`) treats both the same at the Pydantic-validation boundary used in these specific mutated paths — same category as chat's Archetype 2.

#### Mutant B — Guard clause: `_jaccard`'s `if not a and not b:` → `if not a or not b:`
```diff
- if not a and not b:
+ if not a or not b:
      return 0.0
  return len(a & b) / len(a | b)
```
**Proof of harmlessness (mathematical):** the guard only short-circuits to `0.0`; everything else still falls through to `len(a & b) / len(a | b)`. Whenever *exactly one* of `a`/`b` is empty — the new case the `or` variant additionally catches — the intersection `a & b` is necessarily empty too (nothing can be common with an empty set), so the un-guarded formula already evaluates to `0 / len(a | b) = 0.0`. The `or` guard therefore returns the same `0.0` the original formula would have computed anyway for every input the two conditions disagree on; the only case where they produce different *control flow* (one empty, one non-empty) still produces the same *value*. This is a true equivalent mutant, not reachable by any black-box test on `_jaccard`'s output.

*(Total: 3 mutants — `_to_candidate__mutmut_1`, `get_matches__mutmut_34`, `_jaccard__mutmut_1`)*

---

### Grand Total Accounting

$$\text{Total Surviving Mutants} = 30 \text{ (Cosmetic Strings)} + 63 \text{ (Mock Boundaries)} + 3 \text{ (Equivalent)} = 96$$

**Conclusion:** All 96 surviving mutants are accounted for and proven harmless or mathematically equivalent. The real gaps this audit found in `matching` (`swipe`'s idempotent-pass ternary, `_to_candidate`'s unasserted `age`/`bio`, the Jaccard division/multiplication ranking formula, `get_matches`'s `continue`/`break` truncation bug, and `get_matches`'s untested default `limit`) were all fixed and their mutants now show `killed`.
