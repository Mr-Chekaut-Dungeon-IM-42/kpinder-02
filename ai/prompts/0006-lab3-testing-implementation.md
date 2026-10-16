# 0006 — Lab-3 Testing Implementation: Unit, Mutation, Integration, and E2E

Session log: Implementing the complete four-tier testing strategy for Lab-3, focusing on the `chat` slice, mutation auditing via `mutmut`, dedicated test database isolation, and cross-slice black-box E2E user journey testing.

---

### [0006.1] Context & Git Branch Strategy
- **User Request:** Inquire about uvicorn startup commands and port configuration; ask how to layer `lab-3` tests on top of `lab-2` implementation changes while maintaining separate pull requests for both labs.
- **Clarification & Advice:**
  - `uvicorn app.main:app --reload` runs from `backend/` on default port `8000`.
  - Rebase `feat/lab-3` on `feat/lab-2` (`git checkout feat/lab-3 && git rebase feat/lab-2`).
  - Open **stacked PRs** on GitHub:
    - PR 1 (`feat/lab-2` $\rightarrow$ `main`): contains full app implementation.
    - PR 2 (`feat/lab-3` $\rightarrow$ `feat/lab-2`): contains tests and ADRs only, keeping the PR diff completely clean.

---

### [0006.2] Milestone Roadmap Formulation
- **User Request:** Step-by-step guide for writing tests for the `chat` slice according to `spec.md`, simplified into:
  - **M1:** Infra + Unit Tests (full coverage of at least 1 module) + Mutation Testing
  - **M2:** Integration Tests
  - **M3:** E2E Tests
- **Architectural Scope Defined:**
  - Mutation tests are not separate test files; they are an automated audit tool run against unit tests.
  - Integration tests run in-process (`ASGITransport` + in-process WebSocket via `TestClient`) against real Postgres.
  - E2E tests run black-box over actual network sockets (`httpx` + real TCP `websockets` client) across all slices.

---

### [0006.3] Milestone 1: Unit Tests & Branch Coverage (`chat` slice)
- **Implementation:** Created `backend/app/chat/tests/test_service.py` with 27 unit tests mocking `repository` and `ws_manager`.
- **Target Function Coverage:**
  1. `_encode_cursor` / `_decode_cursor`: Base64 serialization, invalid cursor handling (`422`).
  2. `_assert_participant`: Resolves recipient ID; rejects outsiders (`403`).
  3. `send_message`:
     - Happy path (`201`, emits `"new_message"` over WS).
     - Missing match (`404`), non-participant (`403`).
     - Send dedup on `IntegrityError`: catches duplicate `client_message_id`, rolls back DB, returns existing message, and suppresses duplicate WS events.
  4. `get_messages`: Validates boundaries, handles cursor decoding, sets `next_cursor` when limit reached.
  5. `edit_message`: Enforces ownership (`403` for non-sender), updates message, emits `"message_edited"` WS event.
  6. `delete_message`: Hard-deletes message (ADR-0013), emits `"message_deleted"` WS event.
  7. `search_messages`: Short-circuits whitespace queries to `[]`, executes case-insensitive content query.
- **Verification:** 100% statement (93/93) and 100% branch (30/30) coverage.

---

### [0006.4] Mutation Testing & Survivor Classification (`mutmut`)
- **Tool Configuration:** Configured `[tool.mutmut]` in `backend/pyproject.toml` with `source_paths = ["app/chat/service.py"]` and `pytest_add_cli_args_test_selection = ["app/chat/tests/test_service.py"]`.
- **Initial Run:** 274 mutants generated $\rightarrow$ **178 killed (65%)**, **96 survived**.
- **Audit of Surviving Mutants:**
  - **Category 1 (Critical Logic Gaps):**
    - `x_get_messages__mutmut_41` & `42`: Mutant changed `messages[-1].created_at` to `messages[+1]` or `messages[-2]`. Test verified only `msg_id`, ignoring `created_at`.
    - `x_get_messages__mutmut_1`: Mutant changed `limit: int = 20` to `21`. Test explicitly passed `limit=20`, never verifying the default parameter.
  - **Category 2 (Acceptable Mock Argument Gaps):** ~50 mutants replaced `db` or `match_id` arguments with `None` in mocked repository calls (`repository.get_match(None, ...)`). Mocks did not assert parameter signatures. Covered by Integration tier.
  - **Category 3 (Equivalent / Cosmetic):** ~44 mutants altered error `detail` strings (`detail="XXMatch not foundXX"`) or boolean equivalence (`is_new = None` vs `False`).
- **Remediation:**
  - Staggered timestamps in `test_get_messages_generates_next_cursor_when_limit_reached` and asserted `assert dt == messages[-1].created_at`.
  - Called `service.get_messages(..., cursor=None)` without `limit` and asserted `mock_get_page.assert_awaited_once_with(..., 20)`.
  - Re-ran `mutmut` $\rightarrow$ **All critical logic mutants were killed**.

---

### [0006.5] Milestone 2: Integration Tests & Database Isolation
- **Implementation:** Created `backend/app/chat/tests/test_integration.py` containing 5 scenarios:
  1. `test_full_rest_message_lifecycle_and_hard_delete`: Send $\rightarrow$ List $\rightarrow$ Search $\rightarrow$ Edit $\rightarrow$ Hard Delete $\rightarrow$ Direct SQL check that row is permanently deleted.
  2. `test_concurrent_message_dedup_unique_constraint`: Concurrent HTTP sends with same `client_message_id` persist exactly 1 row.
  3. `test_keyset_pagination_real_db`: 25 rows tested across 2 pages without skips or duplicates.
  4. `test_outsider_cannot_access_chat`: Outsider receives `403` on both read and write.
  5. `test_websocket_auth_and_live_events`: Anonymous connection rejected with close code `1008`; valid client receives frames for `"new_message"`, `"message_edited"`, `"message_deleted"`.
- **Database Architecture & Cleanup:**
  - Created dedicated database **`kpinder_test`** on `localhost:5433` to prevent test contamination of local dev data.
  - Fixtures auto-detect local Compose DB on 5433 $\rightarrow$ create `kpinder_test` if missing $\rightarrow$ fallback to `TEST_DATABASE_URL` / `testcontainers`.
  - Cleaned up 63 test user records and cascade dependents from the development database `kpinder`, leaving only real users (`kylian@mbappe.fr.com` and `alex@example.com`).
  - Updated `auth` and `matching` integration tests to use randomized emails and target `kpinder_test`.

---

### [0006.6] Milestone 3: Black-Box E2E Journey Tests
- **Implementation:** Created `backend/tests/test_e2e_journey.py` (`@pytest.mark.e2e`).
- **Design Principles (ADR-0015 & ADR-0016):**
  - Zero internal code imports (`app`, `models`, `service`).
  - Driven over real network sockets against `http://localhost:8000` and `ws://localhost:8000/chat/ws`.
  - Uses standard `httpx.AsyncClient` and native `websockets.connect` over TCP (ADR-0018).
- **User Journey Flow:**
  - Sign up & log in Alice and Bob over HTTP.
  - Update profiles (preferences, bio, age).
  - Mutual swiping: Alice likes Bob, Bob likes Alice $\rightarrow$ mutual match created.
  - Real TCP WebSocket: Bob connects $\rightarrow$ Alice sends, edits, and deletes messages via HTTP REST $\rightarrow$ Bob verifies live push frames over TCP.
  - Hard delete verification: Bob verifies message is absent from chat history.
- **Cross-Slice Rationale:** E2E validates slice composition, contract compatibility, and network transports rather than repeating slice-isolated test logic.

---

### [0006.7] Makefile & Tooling Standardization
- Updated `backend/pyproject.toml` with `e2e` marker and excluded integration/e2e tests from default runs.
- Enhanced root `Makefile` with clean target definitions:
  - `make test` / `make test-unit`: Runs 58 unit tests across slices (~0.9s).
  - `make test-int` / `make test-integration`: Runs 7 integration tests in `kpinder_test` (~1.0s).
  - `make test-mut` / `make mutation`: Runs `mutmut` on `chat/service.py` (~2.5s).
  - `make test-e2e`: Runs full black-box journey against live server (~0.9s).
  - `make test-all`: Runs Unit $\rightarrow$ Integration $\rightarrow$ E2E in sequence (~3.0s).
  - `make lint`: Validates Ruff linting and formatting.
